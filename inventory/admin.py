from django.contrib import admin
from django.urls import reverse, path
from django.utils.html import format_html
from django.contrib import messages
from django.http import HttpResponseRedirect
from django import forms
from django.shortcuts import render
from .models import Product, Client, Order, Provider, RawProduct, Purchase, PurchaseItem, RecipeIngredient, Quote, ProviderCatalog


class IngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 1
    fields = ('raw_product', 'quantity', 'unit', 'notes')
    verbose_name = "Ingrediente"
    verbose_name_plural = "Ingredientes"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'cost', 'price', 'margin_percentage', 'quantity_in_stock', 'is_available')
    list_filter = ('category', 'is_available', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('cost',)
    inlines = [IngredientInline]
    fieldsets = (
        ('Información Básica', {'fields': ('name', 'category', 'description', 'short_description', 'image')}),
        ('Precios', {
            'description': (
                'Selecciona un modo: ingresa el Precio o el Margen — '
                'el otro valor y el Costo se calculan automáticamente desde los ingredientes.'
            ),
            'fields': ('cost', 'pricing_mode', 'price', 'margin_percentage'),
        }),
        ('Stock', {'fields': ('quantity_in_stock', 'reorder_level')}),
        ('Estado', {'fields': ('is_available',)}),
    )

    class Media:
        js = ('admin/js/pricing_mode.js',)

    def save_model(self, request, obj, form, change):
        from decimal import Decimal

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
    list_display = ('name', 'email', 'phone', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'email', 'phone')
    fieldsets = (
        ('Información del Cliente', {'fields': ('name', 'email', 'phone')}),
    )


class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        product  = cleaned.get('product')
        quantity = cleaned.get('quantity')
        if product and quantity:
            shortages = product.check_stock_for(quantity)
            if shortages:
                lines = [
                    f"• {s['name']}: necesitas {s['needed']:.2f} {s['unit']}, "
                    f"disponible {s['available']:.2f} {s['unit']} "
                    f"(falta {s['shortage']:.2f} {s['unit']})"
                    for s in shortages
                ]
                raise forms.ValidationError(
                    "⚠️ No hay suficientes materias primas para producir este pedido:\n" +
                    "\n".join(lines)
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        from decimal import Decimal
        
        # Auto-populate unit_price from product price if not already set
        if instance.product and (not instance.unit_price or instance.unit_price == 0):
            instance.unit_price = instance.product.price
        
        # Auto-calculate total_price from unit_price and quantity
        if instance.unit_price and instance.quantity:
            instance.total_price = (instance.unit_price * Decimal(str(instance.quantity))).quantize(Decimal('0.000001'))
        
        if commit:
            instance.save()
        return instance


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    list_display = ('id', 'client', 'product', 'quantity', 'unit_price', 'total_price', 'status', 'order_date')
    list_filter = ('status', 'order_date', 'client')
    search_fields = ('client__name', 'product__name')
    readonly_fields = ('order_date', 'unit_price', 'total_price')
    fieldsets = (
        ('Detalles del Pedido', {'fields': ('client', 'product', 'quantity', 'unit_price', 'total_price')}),
        ('Estado', {'fields': ('status', 'notes')}),
    )

    def save_model(self, request, obj, form, change):
        from decimal import Decimal
        
        # Auto-populate unit_price from product price if not set
        if obj.product and (not obj.unit_price or obj.unit_price == 0):
            obj.unit_price = obj.product.price
        
        # Auto-calculate total_price
        if obj.unit_price and obj.quantity:
            obj.total_price = (obj.unit_price * Decimal(str(obj.quantity))).quantize(Decimal('0.000001'))
        
        super().save_model(request, obj, form, change)


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'email', 'phone', 'city')
    list_filter = ('city', 'created_at')
    search_fields = ('name', 'contact_person', 'email')
    fieldsets = (
        ('Company Info', {'fields': ('name', 'contact_person', 'email', 'phone')}),
        ('Address', {'fields': ('address', 'city', 'postal_code')}),
    )



class ProviderCatalogInline(admin.TabularInline):
    model = ProviderCatalog
    extra = 1
    fields = ('provider', 'unit_price', 'notes', 'updated_at')
    readonly_fields = ('updated_at',)
    verbose_name = "Provider Price"
    verbose_name_plural = "Provider Prices (sorted cheapest first)"
    ordering = ('unit_price',)


@admin.register(RawProduct)
class RawProductAdmin(admin.ModelAdmin):
    list_display  = ('name', 'brand', 'unit', 'cost_per_unit', 'average_cost', 'quantity_in_stock', 'provider')
    list_filter   = ('unit', 'provider', 'brand', 'created_at')
    search_fields = ('name', 'brand', 'description')
    readonly_fields = ('average_cost',)
    inlines = [ProviderCatalogInline]
    fieldsets = (
        ('Basic Info', {'fields': ('name', 'brand', 'description', 'provider')}),
        ('Units & Cost', {'fields': ('unit', 'cost_per_unit', 'average_cost')}),
        ('Stock', {'fields': ('quantity_in_stock', 'reorder_level')}),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'price-compare/',
                self.admin_site.admin_view(self.price_compare_view),
                name='rawproduct_price_compare',
            ),
        ]
        return custom + urls

    def price_compare_view(self, request):
        raw_products = RawProduct.objects.order_by('name', 'brand')
        selected_id  = request.GET.get('raw_product')
        entries      = []
        selected_rp  = None

        if selected_id:
            try:
                selected_rp = RawProduct.objects.get(pk=selected_id)
                qs = (
                    ProviderCatalog.objects
                    .filter(raw_product=selected_rp)
                    .select_related('provider')
                    .order_by('unit_price')
                )
                # Annotate each entry with the difference vs cheapest
                entries_list = list(qs)
                if entries_list:
                    cheapest = entries_list[0].unit_price
                    for e in entries_list:
                        e.diff_from_cheapest = e.unit_price - cheapest
                entries = entries_list
            except RawProduct.DoesNotExist:
                pass

        context = {
            **self.admin_site.each_context(request),
            'title': 'Price Compare by Provider',
            'raw_products': raw_products,
            'selected_id': int(selected_id) if selected_id else None,
            'selected_rp': selected_rp,
            'entries': entries,
            'opts': RawProduct._meta,
        }
        return render(request, 'admin/inventory/rawproduct/price_compare.html', context)


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
        ('Purchase Info', {'fields': ('provider', 'delivery_date', 'status')}),
        ('Notes', {'fields': ('notes',)}),
    )
    readonly_fields = ('purchase_date', 'get_total_cost')

    def get_total_cost(self, obj):
        return f"${obj.total_cost:.2f}"
    get_total_cost.short_description = 'Total Cost'


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    change_form_template = 'admin/inventory/quote/change_form.html'

    list_display = (
        'id', 'client', 'product', 'quantity', 'unit_price',
        'show_total_price', 'show_delivery_cost', 'show_grand_total',
        'due_date', 'show_days_until_due', 'status',
    )
    list_filter  = ('status', 'due_date', 'client')
    search_fields = ('client__name', 'product__name', 'notes')
    readonly_fields = ('unit_price', 'show_total_price', 'show_grand_total', 'show_days_until_due')
    fieldsets = (
        ('Quote Details', {
            'fields': ('client', 'product', 'quantity', 'unit_price', 'delivery_cost'),
        }),
        ('Totals (auto)', {
            'fields': ('show_total_price', 'show_grand_total'),
        }),
        ('Schedule', {
            'fields': ('due_date', 'show_days_until_due'),
        }),
        ('Status & Notes', {
            'fields': ('status', 'notes'),
        }),
    )

    # ── custom URLs ──────────────────────────────────────────────────────────

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:pk>/convert/',
                self.admin_site.admin_view(self.convert_to_order_view),
                name='quote_convert_to_order',
            ),
        ]
        return custom + urls

    def convert_to_order_view(self, request, pk):
        quote = Quote.objects.select_related('client', 'product').get(pk=pk)

        shortages = quote.product.check_stock_for(quote.quantity)
        if shortages:
            lines = [
                f"• {s['name']}: need {s['needed']:.2f} {s['unit']}, "
                f"available {s['available']:.2f} {s['unit']} "
                f"(short by {s['shortage']:.2f} {s['unit']})"
                for s in shortages
            ]
            messages.error(
                request,
                format_html(
                    "⚠️ Cannot convert: not enough raw materials.<br>{}",
                    format_html("<br>".join(lines)),
                ),
            )
            return HttpResponseRedirect(
                reverse('admin:inventory_quote_change', args=[pk])
            )

        # Create the order
        order = Order.objects.create(
            client=quote.client,
            product=quote.product,
            quantity=quote.quantity,
            unit_price=quote.unit_price,
            total_price=quote.total_price,
            status='pending',
            notes=f"Converted from Quote #{quote.pk}. {quote.notes or ''}".strip(),
        )
        quote.status = 'approved'
        quote.save(update_fields=['status'])

        messages.success(request, f"✅ Quote #{pk} converted to Order #{order.pk}.")
        return HttpResponseRedirect(
            reverse('admin:inventory_order_change', args=[order.pk])
        )

    # ── save logic ───────────────────────────────────────────────────────────

    def save_model(self, request, obj, form, change):
        # Auto-fill unit_price from product price when not set
        if (not obj.unit_price or obj.unit_price == 0) and obj.product_id:
            obj.unit_price = obj.product.price
        super().save_model(request, obj, form, change)

    # ── display helpers ──────────────────────────────────────────────────────

    def show_total_price(self, obj):
        return f"${obj.total_price:.2f}" if obj.pk else "—"
    show_total_price.short_description = "Total Price"

    def show_delivery_cost(self, obj):
        return f"${obj.delivery_cost:.2f}"
    show_delivery_cost.short_description = "Delivery"

    def show_grand_total(self, obj):
        return f"${obj.grand_total:.2f}" if obj.pk else "—"
    show_grand_total.short_description = "Grand Total"

    def show_days_until_due(self, obj):
        if not obj.pk or not obj.due_date:
            return "—"
        days = obj.days_until_due
        if days < 0:
            return format_html(
                '<span style="color:#c00;font-weight:bold;">Overdue by {} day{}</span>',
                abs(days), "s" if abs(days) != 1 else "",
            )
        if days == 0:
            return format_html('<span style="color:#c00;font-weight:bold;">Due today!</span>')
        if days <= 3:
            return format_html(
                '<span style="color:#e65c00;font-weight:bold;">{} day{}</span>',
                days, "s" if days != 1 else "",
            )
        return format_html('<span style="color:#080;">{} days</span>', days)
    show_days_until_due.short_description = "Days Until Due"


@admin.register(ProviderCatalog)
class ProviderCatalogAdmin(admin.ModelAdmin):
    list_display  = ("raw_product", "provider", "unit_price", "updated_at")
    list_filter   = ("provider", "raw_product__brand")
    search_fields = ("raw_product__name", "raw_product__brand", "provider__name")
    readonly_fields = ("updated_at",)
    ordering = ("raw_product", "unit_price")


# Personalizar el sitio admin
class CustomAdminSite(admin.AdminSite):
    site_header = "🥐 Pastelería Yaz - Administración"
    site_title = "Pastelería Yaz"
    index_title = "Panel de Control"
    
    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['dashboard_url'] = reverse('admin_dashboard')
        return super().index(request, extra_context)


# Reemplazar el sitio admin por defecto (opcional)
# admin.site = CustomAdminSite()

