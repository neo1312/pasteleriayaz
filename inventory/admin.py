from django.contrib import admin
from django.urls import reverse, path
from django.utils.html import format_html
from django.contrib import messages
from django.http import HttpResponseRedirect, JsonResponse
from django import forms
from django.shortcuts import render
from django.utils.formats import number_format
from .models import Product, Client, Order, Provider, RawProduct, Purchase, PurchaseItem, RecipeIngredient, Quote, QuoteAgregado, ProviderCatalog, ComplexityTier, TransportZone, BaseBread, Filling, Topping, BaseBreadIngredient, FillingIngredient, ToppingIngredient, Brand, EventTag


class IngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 1
    fields = ('raw_product', 'quantity', 'unit', 'notes')
    verbose_name = "Ingrediente"
    verbose_name_plural = "Ingredientes"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'brand', 'cost', 'price', 'margin_percentage', 'is_available')
    list_filter = ('category', 'brand', 'complexity_tier', 'is_available', 'featured', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('cost',)
    inlines = [IngredientInline]
    fieldsets = (
        ('Información Básica', {'fields': ('name', 'category', 'brand', 'description', 'short_description', 'image')}),
        ('Componentes (Pastel)', {
            'description': 'Solo para productos categoría "Pastel". Selecciona base, relleno y cubierta.',
            'fields': ('base_bread', 'filling', 'topping'),
        }),
        ('Precios', {
            'description': (
                'Selecciona un modo: ingresa el Precio o el Margen — '
                'el otro valor y el Costo se calculan automáticamente desde los ingredientes.'
            ),
            'fields': ('cost', 'pricing_mode', 'price', 'margin_percentage'),
        }),
        ('Raciones', {
            'fields': ('complexity_tier', 'base_labor_per_portion', 'min_persons', 'max_persons'),
        }),
        ('Estado', {'fields': ('is_available', 'show_in_gallery', 'featured')}),
    )

    class Media:
        js = ('admin/js/pricing_mode.js',)

    def save_model(self, request, obj, form, change):
        from decimal import Decimal

        uploaded = request.FILES.get('image')
        if uploaded:
            from .image_utils import save_optimized_product_image
            obj.image = save_optimized_product_image(uploaded)

        # For existing products recalculate cost now; for new ones the product
        # has no pk yet so we can't query ingredients — save_related handles it.
        if obj.pk:
            obj.cost = obj.calculate_cost()

        cost = obj.cost or Decimal('0')

        if obj.pricing_mode == 'price':
            if cost > 0:
                obj.margin_percentage = ((obj.price - cost) / cost * 100).quantize(Decimal('0.01'))
            else:
                obj.margin_percentage = Decimal('0')
        else:
            if cost > 0:
                obj.price = (cost * (1 + obj.margin_percentage / Decimal('100'))).quantize(Decimal('0.000001'))

        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        """Recalculate cost and derived price/margin after ingredients are saved."""
        super().save_related(request, form, formsets, change)
        from decimal import Decimal
        obj = form.instance
        obj.cost = obj.calculate_cost()
        cost = obj.cost or Decimal('0')
        if obj.pricing_mode == 'price':
            if cost > 0:
                obj.margin_percentage = ((obj.price - cost) / cost * 100).quantize(Decimal('0.01'))
            else:
                obj.margin_percentage = Decimal('0')
        else:
            if cost > 0:
                obj.price = (cost * (1 + obj.margin_percentage / Decimal('100'))).quantize(Decimal('0.000001'))
        obj.save(update_fields=['cost', 'price', 'margin_percentage'])


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'user', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'email', 'phone', 'user__username')
    fieldsets = (
        ('Información del Cliente', {'fields': ('name', 'email', 'phone')}),
        ('Usuario', {'fields': ('user',)}),
    )


class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get('product')
        persons = cleaned.get('persons')
        if product and persons:
            shortages = product.check_stock_for(persons)
            if shortages:
                lines = [
                    f"• {s['name']}: necesitas {s['needed']:.2f} {s['unit']}, "
                    f"disponible {s['available']:.2f} {s['unit']} "
                    f"(falta {s['shortage']:.2f} {s['unit']})"
                    for s in shortages
                ]
                raise forms.ValidationError(
                    "⚠️ No hay suficientes materias primas para este pedido:\n" +
                    "\n".join(lines)
                )
        return cleaned


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    list_display = ('id', 'client', 'product', 'persons', 'unit_price', 'total_price', 'grand_total_display', 'deadline', 'stock_verified', 'status', 'order_date')
    list_filter = ('status', 'order_date', 'client', 'stock_verified', 'deadline')
    search_fields = ('client__name', 'product__name')
    readonly_fields = ('order_date', 'unit_price', 'design_surcharge', 'labor_cost', 'total_price', 'grand_total_display')
    fieldsets = (
        ('Detalles del Pedido', {'fields': ('client', 'product', 'persons', 'unit_price', 'total_price', 'grand_total_display')}),
        ('Personalización', {'fields': ('design_notes', 'design_surcharge', 'labor_cost')}),
        ('Envío y Entrega', {'fields': ('delivery_cost', 'deadline', 'stock_verified')}),
        ('Estado', {'fields': ('status', 'notes')}),
    )

    def grand_total_display(self, obj):
        return f"${obj.delivery_cost + obj.total_price:.2f}" if obj.pk else "—"
    grand_total_display.short_description = 'Gran Total'


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'email', 'phone', 'city')
    list_filter = ('city', 'created_at')
    search_fields = ('name', 'contact_person', 'email')
    fieldsets = (
        ('Información de la Empresa', {'fields': ('name', 'contact_person', 'email', 'phone')}),
        ('Dirección', {'fields': ('address', 'city', 'postal_code')}),
    )



class ProviderCatalogInline(admin.TabularInline):
    model = ProviderCatalog
    extra = 1
    fields = ('provider', 'unit_price', 'notes', 'updated_at')
    readonly_fields = ('updated_at',)
    verbose_name = "Precio de Proveedor"
    verbose_name_plural = "Precios de Proveedores (ordenado más barato primero)"
    ordering = ('unit_price',)


@admin.register(RawProduct)
class RawProductAdmin(admin.ModelAdmin):
    list_display  = ('name', 'brand', 'unit', 'cost_per_unit', 'average_cost', 'quantity_in_stock', 'provider')
    list_filter   = ('unit', 'provider', 'brand', 'created_at')
    search_fields = ('name', 'brand__name', 'description')
    readonly_fields = ('average_cost',)
    inlines = [ProviderCatalogInline]
    fieldsets = (
        ('Información Básica', {'fields': ('name', 'brand', 'description', 'provider')}),
        ('Unidades y Costo', {'fields': ('unit', 'cost_per_unit', 'average_cost')}),
        ('Stock', {'fields': ('quantity_in_stock', 'reorder_level')}),
    )


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 1
    fields = ('raw_product', 'quantity', 'unit_cost', 'item_total')
    readonly_fields = ('item_total',)


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'provider', 'status', 'purchase_date', 'delivery_date', 'get_total_cost')
    list_filter = ('status', 'purchase_date', 'provider')
    search_fields = ('provider__name', 'notes')
    inlines = [PurchaseItemInline]
    fieldsets = (
        ('Información de Compra', {'fields': ('provider', 'delivery_date', 'status')}),
        ('Notas', {'fields': ('notes',)}),
    )
    readonly_fields = ('purchase_date', 'get_total_cost')

    def get_total_cost(self, obj):
        return f"${number_format(obj.total_cost, 2)}"
    get_total_cost.short_description = 'Costo Total'


class QuoteAgregadoInline(admin.TabularInline):
    model = QuoteAgregado
    extra = 0
    fields = ('description', 'amount')
    verbose_name = "Agregado"
    verbose_name_plural = "Agregados"


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    change_form_template = 'admin/inventory/quote/change_form.html'

    list_display = (
        'id', 'client', 'cake_name', 'persons', 'unit_price',
        'show_total_price', 'show_delivery_cost', 'show_grand_total',
        'due_date', 'show_days_until_due', 'status',
    )
    list_filter  = ('status', 'due_date', 'client')
    search_fields = ('client__name', 'name', 'notes')
    readonly_fields = ('unit_price', 'ingredient_cost', 'labor_cost', 'benefit_amount', 'design_surcharge', 'extras_amount', 'show_total_price', 'show_grand_total', 'show_days_until_due')
    inlines = [QuoteAgregadoInline]
    fieldsets = (
        ('Detalles de Cotización', {
            'fields': ('client', 'name', 'base_bread', 'filling', 'topping', 'complexity_tier', 'persons', 'design_notes'),
        }),
        ('Precio', {
            'fields': ('benefit_percentage', 'unit_price'),
        }),
        ('Costos (auto)', {
            'fields': ('ingredient_cost', 'labor_cost', 'design_surcharge', 'benefit_amount', 'extras_amount', 'delivery_cost'),
        }),
        ('Producto (se crea al vender)', {
            'fields': ('product',),
        }),
        ('Totales (auto)', {
            'fields': ('show_total_price', 'show_grand_total'),
        }),
        ('Programación', {
            'fields': ('due_date', 'show_days_until_due'),
        }),
        ('Estado y Notas', {
            'fields': ('status', 'notes'),
        }),
    )

    class Media:
        js = ('admin/js/quote_autofill.js',)

    # ── custom URLs ──────────────────────────────────────────────────────────

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:pk>/convert/',
                self.admin_site.admin_view(self.convert_to_order_view),
                name='quote_convert_to_order',
            ),
            path(
                'product-price/<int:product_id>/',
                self.admin_site.admin_view(self.product_price_view),
                name='quote_product_price',
            ),
        ]
        return custom + urls

    def product_price_view(self, request, product_id):
        try:
            product = Product.objects.get(pk=product_id)
            breakdown = product.calculate_price_for(1)
            return JsonResponse({
                'price_per_person': str(breakdown['price_per_person']),
                'ingredient_cost': str(breakdown['ingredient_cost']),
                'labor_cost': str(breakdown['labor_cost']),
                'base_total': str(breakdown['base_total']),
                'design_surcharge': str(breakdown['design_surcharge']),
                'total': str(breakdown['total']),
            })
        except Product.DoesNotExist:
            return JsonResponse({'price': '0'}, status=404)

    def convert_to_order_view(self, request, pk):
        quote = Quote.objects.select_related('client', 'product').get(pk=pk)

        product = quote.ensure_product()
        quote.refresh_from_db()

        shortages = product.check_stock_for(quote.persons)
        if shortages:
            lines = [
                f"• {s['name']}: necesita {s['needed']:.2f} {s['unit']}, "
                f"disponible {s['available']:.2f} {s['unit']} "
                f"(falta {s['shortage']:.2f} {s['unit']})"
                for s in shortages
            ]
            messages.error(
                request,
                format_html(
                    "⚠️ No se puede convertir: no hay suficientes materias primas.<br>{}",
                    format_html("<br>".join(lines)),
                ),
            )
            return HttpResponseRedirect(
                reverse('admin:inventory_quote_change', args=[pk])
            )

        quote.recalculate()

        # Create the order
        order = Order.objects.create(
            client=quote.client,
            product=product,
            persons=quote.persons,
            unit_price=quote.unit_price,
            design_notes=quote.design_notes,
            design_surcharge=quote.design_surcharge,
            labor_cost=quote.labor_cost,
            total_price=quote.total_price,
            delivery_cost=quote.delivery_cost,
            status='pending',
            notes=f"Convertido de Cotización #{quote.pk}. {quote.notes or ''}".strip(),
        )
        Order.objects.filter(pk=order.pk).update(
            unit_price=quote.unit_price,
            design_surcharge=quote.design_surcharge,
            labor_cost=quote.labor_cost,
            total_price=quote.total_price,
        )
        quote.status = 'approved'
        quote.save(update_fields=['status'])

        messages.success(request, f"✅ Cotización #{pk} convertida a Pedido #{order.pk}.")
        return HttpResponseRedirect(
            reverse('admin:inventory_order_change', args=[order.pk])
        )

    # ── save logic ───────────────────────────────────────────────────────────

    def save_model(self, request, obj, form, change):
        obj.recalculate()
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        """Recalculate after M2M agregados are saved."""
        super().save_related(request, form, formsets, change)
        obj = form.instance
        obj.recalculate()
        obj.save(update_fields=['extras_amount', 'ingredient_cost', 'labor_cost', 'design_surcharge', 'benefit_amount', 'unit_price'])

    # ── display helpers ──────────────────────────────────────────────────────

    def show_total_price(self, obj):
        return f"${number_format(obj.total_price, 2)}" if obj.pk else "—"
    show_total_price.short_description = "Precio Total"

    def show_delivery_cost(self, obj):
        return f"${number_format(obj.delivery_cost, 2)}"
    show_delivery_cost.short_description = "Envío"

    def show_grand_total(self, obj):
        return f"${number_format(obj.grand_total, 2)}" if obj.pk else "—"
    show_grand_total.short_description = "Gran Total"

    def show_days_until_due(self, obj):
        if not obj.pk or not obj.due_date:
            return "—"
        days = obj.days_until_due
        if days < 0:
            return format_html(
                '<span style="color:#c00;font-weight:bold;">Vencido hace {} día{}</span>',
                abs(days), "s" if abs(days) != 1 else "",
            )
        if days == 0:
            return format_html('<span style="color:#c00;font-weight:bold;">¡Vence hoy!</span>')
        if days <= 3:
            return format_html(
                '<span style="color:#e65c00;font-weight:bold;">{} día{}</span>',
                days, "s" if days != 1 else "",
            )
        return format_html('<span style="color:#080;">{} días</span>', days)
    show_days_until_due.short_description = "Días hasta Vencimiento"


@admin.register(ProviderCatalog)
class ProviderCatalogAdmin(admin.ModelAdmin):
    list_display  = ("raw_product", "provider", "unit_price", "updated_at")
    list_filter   = ("provider", "raw_product__brand")
    search_fields = ("raw_product__name", "raw_product__brand__name", "provider__name")
    readonly_fields = ("updated_at",)
    ordering = ("raw_product", "unit_price")


@admin.register(ComplexityTier)
class ComplexityTierAdmin(admin.ModelAdmin):
    list_display = ("name", "surcharge_percentage")
    search_fields = ("name",)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name', 'description')
    fieldsets = (
        ('Información', {'fields': ('name', 'description')}),
    )


@admin.register(EventTag)
class EventTagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(TransportZone)
class TransportZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "radius_km", "base_fee", "fee_per_km")
    search_fields = ("name",)


# ── Base Bread ─────────────────────────────────────────────────────────────────


class BaseBreadIngredientInline(admin.TabularInline):
    model = BaseBreadIngredient
    extra = 1
    fields = ('raw_product', 'quantity', 'notes')
    verbose_name = "Ingrediente"
    verbose_name_plural = "Ingredientes"


@admin.register(BaseBread)
class BaseBreadAdmin(admin.ModelAdmin):
    list_display = ('name', 'base_labor_per_portion', 'is_available')
    list_filter = ('is_available',)
    search_fields = ('name', 'description')
    inlines = [BaseBreadIngredientInline]
    fieldsets = (
        ('Información Básica', {'fields': ('name', 'description')}),
        ('Costos', {'fields': ('base_labor_per_portion',)}),
        ('Estado', {'fields': ('is_available',)}),
    )


# ── Filling ────────────────────────────────────────────────────────────────────


class FillingIngredientInline(admin.TabularInline):
    model = FillingIngredient
    extra = 1
    fields = ('raw_product', 'quantity', 'notes')
    verbose_name = "Ingrediente"
    verbose_name_plural = "Ingredientes"


@admin.register(Filling)
class FillingAdmin(admin.ModelAdmin):
    list_display = ('name', 'base_labor_per_portion', 'is_available')
    list_filter = ('is_available',)
    search_fields = ('name', 'description')
    inlines = [FillingIngredientInline]
    fieldsets = (
        ('Información Básica', {'fields': ('name', 'description')}),
        ('Costos', {'fields': ('base_labor_per_portion',)}),
        ('Estado', {'fields': ('is_available',)}),
    )


# ── Topping ────────────────────────────────────────────────────────────────────


class ToppingIngredientInline(admin.TabularInline):
    model = ToppingIngredient
    extra = 1
    fields = ('raw_product', 'quantity', 'notes')
    verbose_name = "Ingrediente"
    verbose_name_plural = "Ingredientes"


@admin.register(Topping)
class ToppingAdmin(admin.ModelAdmin):
    list_display = ('name', 'base_labor_per_portion', 'is_available')
    list_filter = ('is_available',)
    search_fields = ('name', 'description')
    inlines = [ToppingIngredientInline]
    fieldsets = (
        ('Información Básica', {'fields': ('name', 'description')}),
        ('Costos', {'fields': ('base_labor_per_portion',)}),
        ('Estado', {'fields': ('is_available',)}),
    )


