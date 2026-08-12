from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count, Q, F
from django.template.loader import render_to_string
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
import json
import io
from weasyprint import HTML
from .models import Product, Order, Purchase, RawProduct, Client, Quote, ProviderCatalog, ComplexityTier, Provider, BaseBread, Filling, Topping, Brand, BaseBreadIngredient, FillingIngredient, ToppingIngredient, EventTag, calculate_components_cost
from .image_utils import save_optimized_product_image


def parse_decimal(value, default=Decimal('0')):
    """Safely parse a decimal from form input (handles commas and empty values)."""
    if value is None:
        return default
    value = str(value).strip().replace(',', '.')
    if not value:
        return default
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return default


def product_gallery(request):
    products = Product.objects.filter(is_available=True, show_in_gallery=True)
    featured_products = products.filter(featured=True)
    category = request.GET.get('category')
    tag_id = request.GET.get('tag')
    gender = request.GET.get('gender')
    if category:
        products = products.filter(category=category)
    if tag_id:
        products = products.filter(event_tags__id=tag_id)
    if gender:
        products = products.filter(gender=gender)
    products = products.order_by('name')
    categories = Product.CATEGORY_CHOICES
    event_tags = EventTag.objects.order_by('name')
    return render(request, 'inventory/gallery.html', {
        'products': products, 'categories': categories,
        'featured_products': featured_products,
        'selected_category': category, 'event_tags': event_tags,
        'selected_tag': int(tag_id) if tag_id else None,
        'selected_gender': gender,
    })


def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_available=True)
    price_info = product.calculate_price_for(product.min_persons or 1)
    return render(request, 'inventory/product_detail.html', {'product': product, 'price_info': price_info})


@login_required
@login_required
def control_dashboard(request):
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    context = {
        'total_products': Product.objects.count(),
        'total_clients': Client.objects.count(),
        'pending_orders': Order.objects.filter(status='pending').count(),
        'low_stock': RawProduct.objects.filter(quantity_in_stock__lt=F('reorder_level')),
        'week_sales_total': Order.objects.filter(status='completed', order_date__date__gte=week_ago).aggregate(total=Sum('total_price'))['total'] or Decimal('0'),
        'week_sales_count': Order.objects.filter(status='completed', order_date__date__gte=week_ago).count(),
        'recent_orders': Order.objects.select_related('client', 'product').order_by('-order_date')[:10],
        'recent_quotes': Quote.objects.select_related('client', 'product').order_by('-created_at')[:10],
        'total_quotes': Quote.objects.count(),
        'pending_quotes': Quote.objects.filter(status='draft').count(),
    }
    return render(request, 'control/dashboard.html', context)


@login_required
def quote_edit(request, pk):
    quote = get_object_or_404(Quote, pk=pk)
    if request.method == 'POST':
        try:
            quote.client = Client.objects.get(id=request.POST['client'])
            quote.persons = int(request.POST['persons'])
            quote.name = request.POST.get('name', '').strip() or quote.cake_name
            quote.base_bread_id = request.POST.get('base_bread') or None
            quote.filling_id = request.POST.get('filling') or None
            quote.topping_id = request.POST.get('topping') or None
            quote.complexity_tier_id = request.POST.get('complexity_tier') or None
            quote.benefit_percentage = parse_decimal(request.POST.get('benefit', '50'))
            quote.design_notes = request.POST.get('design_notes', '').strip()
            quote.delivery_cost = parse_decimal(request.POST.get('delivery_cost', '0'))
            quote.show_delivery_on_pdf = request.POST.get('show_delivery_on_pdf') == 'on'
            quote.due_date = request.POST.get('due_date', None) or None
            quote.recalculate()
            quote.save()
            messages.success(request, f'Cotización #{quote.id} actualizada.')
            return redirect('quotes_list')
        except (ValueError, KeyError):
            messages.error(request, 'Datos inválidos.')

    return render(request, 'control/quote_form.html', {
        'breads': BaseBread.objects.filter(is_available=True),
        'fillings': Filling.objects.filter(is_available=True),
        'toppings': Topping.objects.filter(is_available=True),
        'tiers': ComplexityTier.objects.all(),
        'clients': Client.objects.order_by('name'),
        'quote': quote,
    })


@login_required
def quote_delete(request, pk):
    quote = get_object_or_404(Quote, pk=pk)
    if request.method == 'POST':
        quote.delete()
        messages.success(request, 'Cotización eliminada.')
        return redirect('quotes_list')
    return render(request, 'control/confirm_delete.html', {
        'object': quote,
        'cancel_url': 'quotes_list',
    })


@login_required
def quote_send(request, pk):
    quote = get_object_or_404(Quote, pk=pk)
    if quote.status == 'draft':
        quote.status = 'sent'
        quote.save(update_fields=['status'])
        messages.success(request, f'Cotización #{quote.id} enviada al cliente.')
    return redirect('quotes_list')


@login_required
def quote_approve(request, pk):
    quote = get_object_or_404(Quote, pk=pk)
    if quote.status == 'sent':
        quote.status = 'accepted'
        quote.save(update_fields=['status'])
        product = quote.ensure_product()
        order = Order.objects.create(
            client=quote.client,
            product=product,
            persons=quote.persons,
            unit_price=quote.unit_price,
            design_notes=quote.design_notes,
            design_surcharge=quote.design_surcharge,
            labor_cost=quote.labor_cost,
            delivery_cost=quote.delivery_cost,
            total_price=quote.total_price,
            notes=f"Convertido de Cotización #{quote.pk}",
        )
        Order.objects.filter(pk=order.pk).update(
            unit_price=quote.unit_price,
            design_surcharge=quote.design_surcharge,
            labor_cost=quote.labor_cost,
            total_price=quote.total_price,
        )
        messages.success(request, f'Cotización #{quote.pk} aprobada. Pedido creado.')
    return redirect('quotes_list')


@login_required
def quotes_list(request):
    quotes = Quote.objects.select_related('client', 'product').order_by('-created_at')
    status_filter = request.GET.get('status')
    if status_filter:
        quotes = quotes.filter(status=status_filter)
    return render(request, 'control/quotes.html', {
        'quotes': quotes,
        'status_filter': status_filter,
        'status_choices': Quote.STATUS_CHOICES,
    })


# ── Products CRUD ────────────────────────────────────────────────────────────

@login_required
def product_list(request):
    products = Product.objects.all().order_by('name')
    search = request.GET.get('search', '')
    category = request.GET.get('category', '')
    if search:
        products = products.filter(name__icontains=search)
    if category:
        products = products.filter(category=category)
    return render(request, 'control/product_list.html', {
        'products': products,
        'search': search,
        'category': category,
        'categories': Product.CATEGORY_CHOICES,
    })


@login_required
def product_create(request):
    tiers = ComplexityTier.objects.all()
    breads = BaseBread.objects.filter(is_available=True)
    fillings = Filling.objects.filter(is_available=True)
    toppings = Topping.objects.filter(is_available=True)
    brands = Brand.objects.order_by('name')
    tags = EventTag.objects.order_by('name')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'El nombre es obligatorio.')
            return render(request, 'control/product_form.html', {'form': request.POST, 'tiers': tiers, 'breads': breads, 'fillings': fillings, 'toppings': toppings, 'brands': brands, 'tags': tags})
        product = Product(
            name=name,
            category=request.POST.get('category', 'other'),
            description=request.POST.get('description', ''),
            short_description=request.POST.get('short_description', ''),
            price=parse_decimal(request.POST.get('price', '0')),
            is_available=request.POST.get('is_available') == 'on',
            show_in_gallery=request.POST.get('show_in_gallery') == 'on',
            featured=request.POST.get('featured') == 'on',
            design_description=request.POST.get('design_description', ''),
            color_scheme=request.POST.get('color_scheme', ''),
            gender=request.POST.get('gender', ''),
        )
        if request.POST.get('base_bread'):
            product.base_bread_id = int(request.POST['base_bread'])
        if request.POST.get('filling'):
            product.filling_id = int(request.POST['filling'])
        if request.POST.get('topping'):
            product.topping_id = int(request.POST['topping'])
        if request.POST.get('brand'):
            product.brand_id = int(request.POST['brand'])
        if request.POST.get('complexity_tier'):
            product.complexity_tier_id = int(request.POST['complexity_tier'])
        if request.POST.get('base_labor_per_portion'):
            product.base_labor_per_portion = parse_decimal(request.POST['base_labor_per_portion'])
        if request.POST.get('min_persons'):
            product.min_persons = int(request.POST['min_persons'])
        if request.POST.get('max_persons'):
            product.max_persons = int(request.POST['max_persons'])
        image_file = save_optimized_product_image(request.FILES.get('image'))
        if image_file:
            product.image = image_file
        product.save()
        event_tag_ids = request.POST.getlist('event_tags')
        if event_tag_ids:
            product.event_tags.set(EventTag.objects.filter(id__in=event_tag_ids))
        messages.success(request, f'Producto "{product.name}" creado.')
        return redirect('product_list')
    return render(request, 'control/product_form.html', {'tiers': tiers, 'breads': breads, 'fillings': fillings, 'toppings': toppings, 'brands': brands, 'tags': tags})


@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    tiers = ComplexityTier.objects.all()
    breads = BaseBread.objects.filter(is_available=True)
    fillings = Filling.objects.filter(is_available=True)
    toppings = Topping.objects.filter(is_available=True)
    brands = Brand.objects.order_by('name')
    tags = EventTag.objects.order_by('name')
    if request.method == 'POST':
        product.name = request.POST.get('name', product.name)
        product.category = request.POST.get('category', product.category)
        product.description = request.POST.get('description', product.description)
        product.short_description = request.POST.get('short_description', product.short_description or '')
        product.price = parse_decimal(request.POST.get('price', '0'))
        product.base_bread_id = request.POST.get('base_bread') or None
        product.filling_id = request.POST.get('filling') or None
        product.topping_id = request.POST.get('topping') or None
        product.brand_id = request.POST.get('brand') or None
        product.complexity_tier_id = request.POST.get('complexity_tier') or None
        product.base_labor_per_portion = parse_decimal(request.POST.get('base_labor_per_portion', '0'))
        product.min_persons = int(request.POST.get('min_persons', '1'))
        product.max_persons = int(request.POST.get('max_persons', '100'))
        product.is_available = request.POST.get('is_available') == 'on'
        product.show_in_gallery = request.POST.get('show_in_gallery') == 'on'
        product.featured = request.POST.get('featured') == 'on'
        product.design_description = request.POST.get('design_description', product.design_description or '')
        product.color_scheme = request.POST.get('color_scheme', product.color_scheme or '')
        product.gender = request.POST.get('gender', product.gender or '')
        image_file = save_optimized_product_image(request.FILES.get('image'))
        if image_file:
            product.image = image_file
        product.save()
        event_tag_ids = request.POST.getlist('event_tags')
        if event_tag_ids:
            product.event_tags.set(EventTag.objects.filter(id__in=event_tag_ids))
        else:
            product.event_tags.clear()
        messages.success(request, f'Producto "{product.name}" actualizado.')
        return redirect('product_list')
    return render(request, 'control/product_form.html', {
        'form': product, 'object': product, 'tiers': tiers,
        'breads': breads, 'fillings': fillings, 'toppings': toppings,
        'brands': brands, 'tags': tags,
    })


@login_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.delete()
        messages.success(request, 'Producto eliminado.')
        return redirect('product_list')
    return render(request, 'control/confirm_delete.html', {'object': product, 'cancel_url': 'product_list'})


# ── Clients CRUD ─────────────────────────────────────────────────────────────

@login_required
def client_list(request):
    clients = Client.objects.order_by('name')
    search = request.GET.get('search', '')
    if search:
        clients = clients.filter(Q(name__icontains=search) | Q(email__icontains=search))
    return render(request, 'control/client_list.html', {'clients': clients, 'search': search})


@login_required
def client_create(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
            name = data.get('name', '').strip()
            email = data.get('email', '').strip()
            if not name or not email:
                return JsonResponse({'error': 'Nombre y email obligatorios'}, status=400) if request.headers.get('X-Requested-With') == 'XMLHttpRequest' else None
            client = Client.objects.create(name=name, email=email, phone=data.get('phone', '').strip())
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'id': client.id, 'name': client.name, 'email': client.email})
            messages.success(request, f'Cliente "{client.name}" creado.')
            return redirect('client_list')
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': str(e)}, status=400)
            messages.error(request, str(e))
    return render(request, 'control/client_form.html')


@login_required
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        client.name = request.POST.get('name', client.name)
        client.email = request.POST.get('email', client.email)
        client.phone = request.POST.get('phone', client.phone)
        client.save()
        messages.success(request, f'Cliente "{client.name}" actualizado.')
        return redirect('client_list')
    return render(request, 'control/client_form.html', {'object': client})


@login_required
def client_delete(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        client.delete()
        messages.success(request, 'Cliente eliminado.')
        return redirect('client_list')
    return render(request, 'control/confirm_delete.html', {'object': client, 'cancel_url': 'client_list'})


# ── Orders CRUD ──────────────────────────────────────────────────────────────

@login_required
def order_list(request):
    orders = Order.objects.select_related('client', 'product').order_by('-order_date')
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(status=status_filter)
    return render(request, 'control/order_list.html', {
        'orders': orders,
        'status_filter': status_filter,
        'status_choices': Order.STATUS_CHOICES,
    })


@login_required
def order_edit(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        order.client_id = request.POST.get('client')
        order.product_id = request.POST.get('product')
        order.persons = int(request.POST.get('persons', '1'))
        order.delivery_cost = parse_decimal(request.POST.get('delivery_cost', '0'))
        order.deadline = request.POST.get('deadline') or None
        order.status = request.POST.get('status', order.status)
        order.notes = request.POST.get('notes', '')
        order.save()
        messages.success(request, f'Pedido #{order.id} actualizado.')
        return redirect('order_list')
    return render(request, 'control/order_form.html', {
        'object': order,
        'clients': Client.objects.order_by('name'),
        'products': Product.objects.filter(is_available=True).order_by('name'),
        'status_choices': Order.STATUS_CHOICES,
    })


@login_required
def order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        order.delete()
        messages.success(request, 'Pedido eliminado.')
        return redirect('order_list')
    return render(request, 'control/confirm_delete.html', {'object': order, 'cancel_url': 'order_list'})


# ── Raw Products CRUD ────────────────────────────────────────────────────────

@login_required
def rawproduct_list(request):
    materials = RawProduct.objects.select_related('provider').order_by('name')
    search = request.GET.get('search', '')
    if search:
        materials = materials.filter(Q(name__icontains=search) | Q(brand__name__icontains=search))
    return render(request, 'control/rawproduct_list.html', {'materials': materials, 'search': search})


@login_required
def rawproduct_create(request):
    providers = Provider.objects.order_by('name')
    brands = Brand.objects.order_by('name')
    if request.method == 'POST':
        rp = RawProduct(
            name=request.POST.get('name', '').strip(),
            brand_id=request.POST.get('brand') or None,
            unit=request.POST.get('unit', 'kg'),
            cost_per_unit=parse_decimal(request.POST.get('cost_per_unit', '0')),
            quantity_in_stock=parse_decimal(request.POST.get('quantity_in_stock', '0')),
            reorder_level=parse_decimal(request.POST.get('reorder_level', '10')),
            provider_id=request.POST.get('provider') or None,
        )
        rp.save()
        messages.success(request, f'Insumo "{rp.name}" creado.')
        return redirect('rawproduct_list')
    return render(request, 'control/rawproduct_form.html', {
        'providers': providers,
        'brands': brands,
        'units': RawProduct.UNIT_CHOICES,
    })


@login_required
def rawproduct_edit(request, pk):
    rp = get_object_or_404(RawProduct, pk=pk)
    providers = Provider.objects.order_by('name')
    brands = Brand.objects.order_by('name')
    if request.method == 'POST':
        rp.name = request.POST.get('name', rp.name)
        rp.brand_id = request.POST.get('brand') or None
        rp.unit = request.POST.get('unit', rp.unit)
        rp.cost_per_unit = parse_decimal(request.POST.get('cost_per_unit', '0'))
        rp.quantity_in_stock = parse_decimal(request.POST.get('quantity_in_stock', '0'))
        rp.reorder_level = parse_decimal(request.POST.get('reorder_level', '10'))
        rp.provider_id = request.POST.get('provider') or None
        rp.save()
        messages.success(request, f'Insumo "{rp.name}" actualizado.')
        return redirect('rawproduct_list')
    return render(request, 'control/rawproduct_form.html', {
        'object': rp,
        'providers': providers,
        'brands': brands,
        'units': RawProduct.UNIT_CHOICES,
    })


@login_required
def rawproduct_delete(request, pk):
    rp = get_object_or_404(RawProduct, pk=pk)
    if request.method == 'POST':
        rp.delete()
        messages.success(request, 'Insumo eliminado.')
        return redirect('rawproduct_list')
    return render(request, 'control/confirm_delete.html', {'object': rp, 'cancel_url': 'rawproduct_list'})


# ── Providers CRUD ───────────────────────────────────────────────────────────

@login_required
def provider_list(request):
    return render(request, 'control/provider_list.html', {
        'providers': Provider.objects.order_by('name'),
    })


@login_required
def provider_create(request):
    if request.method == 'POST':
        p = Provider(
            name=request.POST.get('name', '').strip(),
            contact_person=request.POST.get('contact_person', '').strip(),
            email=request.POST.get('email', '').strip(),
            phone=request.POST.get('phone', '').strip(),
            address=request.POST.get('address', '').strip(),
            city=request.POST.get('city', '').strip(),
            postal_code=request.POST.get('postal_code', '').strip(),
        )
        p.save()
        messages.success(request, f'Proveedor "{p.name}" creado.')
        return redirect('provider_list')
    return render(request, 'control/provider_form.html')


@login_required
def provider_edit(request, pk):
    p = get_object_or_404(Provider, pk=pk)
    if request.method == 'POST':
        p.name = request.POST.get('name', p.name)
        p.contact_person = request.POST.get('contact_person', p.contact_person)
        p.email = request.POST.get('email', p.email)
        p.phone = request.POST.get('phone', p.phone)
        p.address = request.POST.get('address', p.address)
        p.city = request.POST.get('city', p.city)
        p.postal_code = request.POST.get('postal_code', p.postal_code)
        p.save()
        messages.success(request, f'Proveedor "{p.name}" actualizado.')
        return redirect('provider_list')
    return render(request, 'control/provider_form.html', {'object': p})


@login_required
def provider_delete(request, pk):
    p = get_object_or_404(Provider, pk=pk)
    if request.method == 'POST':
        p.delete()
        messages.success(request, 'Proveedor eliminado.')
        return redirect('provider_list')
    return render(request, 'control/confirm_delete.html', {'object': p, 'cancel_url': 'provider_list'})


# ── ComplexityTier CRUD ──────────────────────────────────────────────────────

@login_required
def complexity_tier_list(request):
    return render(request, 'control/complexitytier_list.html', {
        'tiers': ComplexityTier.objects.all(),
    })


@login_required
def complexity_tier_create(request):
    if request.method == 'POST':
        t = ComplexityTier(
            name=request.POST.get('name', '').strip(),
            surcharge_percentage=request.POST.get('surcharge_percentage', 0),
            description=request.POST.get('description', '').strip(),
        )
        t.save()
        messages.success(request, f'Nivel "{t.name}" creado.')
        return redirect('complexity_tier_list')
    return render(request, 'control/complexitytier_form.html')


@login_required
def complexity_tier_edit(request, pk):
    t = get_object_or_404(ComplexityTier, pk=pk)
    if request.method == 'POST':
        t.name = request.POST.get('name', t.name)
        t.surcharge_percentage = request.POST.get('surcharge_percentage', t.surcharge_percentage)
        t.description = request.POST.get('description', t.description)
        t.save()
        messages.success(request, f'Nivel "{t.name}" actualizado.')
        return redirect('complexity_tier_list')
    return render(request, 'control/complexitytier_form.html', {'object': t})


@login_required
def complexity_tier_delete(request, pk):
    t = get_object_or_404(ComplexityTier, pk=pk)
    if request.method == 'POST':
        t.delete()
        messages.success(request, 'Nivel de complejidad eliminado.')
        return redirect('complexity_tier_list')
    return render(request, 'control/confirm_delete.html', {'object': t, 'cancel_url': 'complexity_tier_list'})


# ── BaseBread CRUD ───────────────────────────────────────────────────────────

@login_required
def base_bread_list(request):
    breads = BaseBread.objects.order_by('name')
    search = request.GET.get('search', '')
    if search:
        breads = breads.filter(name__icontains=search)
    return render(request, 'control/basebread_list.html', {'breads': breads, 'search': search})


@login_required
def base_bread_create(request):
    if request.method == 'POST':
        b = BaseBread(
            name=request.POST.get('name', '').strip(),
            description=request.POST.get('description', '').strip(),
            base_labor_per_portion=parse_decimal(request.POST.get('base_labor_per_portion', '0')),
            is_available=request.POST.get('is_available') == 'on',
        )
        b.save()
        messages.success(request, f'Base "{b.name}" creada.')
        return redirect('base_bread_edit', pk=b.pk)
    return render(request, 'control/basebread_form.html')


@login_required
def base_bread_edit(request, pk):
    b = get_object_or_404(BaseBread, pk=pk)
    ingredients = b.ingredients.select_related('raw_product').order_by('raw_product__name')
    raw_products = RawProduct.objects.order_by('name')
    if request.method == 'POST':
        b.name = request.POST.get('name', b.name)
        b.description = request.POST.get('description', b.description)
        b.base_labor_per_portion = parse_decimal(request.POST.get('base_labor_per_portion', '0'))
        b.is_available = request.POST.get('is_available') == 'on'
        b.save()
        messages.success(request, f'Base "{b.name}" actualizada.')
        return redirect('base_bread_edit', pk=b.pk)
    return render(request, 'control/basebread_form.html', {
        'object': b, 'ingredients': ingredients, 'raw_products': raw_products,
    })


@login_required
def base_bread_delete(request, pk):
    b = get_object_or_404(BaseBread, pk=pk)
    if request.method == 'POST':
        b.delete()
        messages.success(request, 'Base eliminada.')
        return redirect('base_bread_list')
    return render(request, 'control/confirm_delete.html', {'object': b, 'cancel_url': 'base_bread_list'})


@login_required
@require_POST
def base_bread_add_ingredient(request, pk):
    b = get_object_or_404(BaseBread, pk=pk)
    rp_id = request.POST.get('raw_product')
    qty = request.POST.get('quantity', '0')
    notes = request.POST.get('notes', '').strip()
    if rp_id and Decimal(qty) > 0:
        BaseBreadIngredient.objects.update_or_create(
            base_bread=b,
            raw_product_id=rp_id,
            defaults={'quantity': qty, 'notes': notes},
        )
        messages.success(request, 'Ingrediente agregado.')
    return redirect('base_bread_edit', pk=b.pk)


@login_required
@require_POST
def base_bread_delete_ingredient(request, pk, ing_pk):
    ing = get_object_or_404(BaseBreadIngredient, pk=ing_pk, base_bread_id=pk)
    ing.delete()
    messages.success(request, 'Ingrediente eliminado.')
    return redirect('base_bread_edit', pk=pk)


@login_required
@require_POST
def base_bread_edit_ingredient(request, pk, ing_pk):
    ing = get_object_or_404(BaseBreadIngredient, pk=ing_pk, base_bread_id=pk)
    rp_id = request.POST.get('raw_product')
    qty = request.POST.get('quantity', '0')
    notes = request.POST.get('notes', '').strip()
    if rp_id and Decimal(qty) > 0:
        ing.raw_product_id = rp_id
        ing.quantity = qty
        ing.notes = notes
        ing.save()
        messages.success(request, 'Ingrediente actualizado.')
    return redirect('base_bread_edit', pk=pk)


# ── Filling CRUD ─────────────────────────────────────────────────────────────

@login_required
def filling_list(request):
    fillings = Filling.objects.order_by('name')
    search = request.GET.get('search', '')
    if search:
        fillings = fillings.filter(name__icontains=search)
    return render(request, 'control/filling_list.html', {'fillings': fillings, 'search': search})


@login_required
def filling_create(request):
    if request.method == 'POST':
        f = Filling(
            name=request.POST.get('name', '').strip(),
            description=request.POST.get('description', '').strip(),
            base_labor_per_portion=parse_decimal(request.POST.get('base_labor_per_portion', '0')),
            is_available=request.POST.get('is_available') == 'on',
        )
        f.save()
        messages.success(request, f'Relleno "{f.name}" creado.')
        return redirect('filling_edit', pk=f.pk)
    return render(request, 'control/filling_form.html')


@login_required
def filling_edit(request, pk):
    f = get_object_or_404(Filling, pk=pk)
    ingredients = f.ingredients.select_related('raw_product').order_by('raw_product__name')
    raw_products = RawProduct.objects.order_by('name')
    if request.method == 'POST':
        f.name = request.POST.get('name', f.name)
        f.description = request.POST.get('description', f.description)
        f.base_labor_per_portion = parse_decimal(request.POST.get('base_labor_per_portion', '0'))
        f.is_available = request.POST.get('is_available') == 'on'
        f.save()
        messages.success(request, f'Relleno "{f.name}" actualizado.')
        return redirect('filling_edit', pk=f.pk)
    return render(request, 'control/filling_form.html', {
        'object': f, 'ingredients': ingredients, 'raw_products': raw_products,
    })


@login_required
def filling_delete(request, pk):
    f = get_object_or_404(Filling, pk=pk)
    if request.method == 'POST':
        f.delete()
        messages.success(request, 'Relleno eliminado.')
        return redirect('filling_list')
    return render(request, 'control/confirm_delete.html', {'object': f, 'cancel_url': 'filling_list'})


@login_required
@require_POST
def filling_add_ingredient(request, pk):
    f = get_object_or_404(Filling, pk=pk)
    rp_id = request.POST.get('raw_product')
    qty = request.POST.get('quantity', '0')
    notes = request.POST.get('notes', '').strip()
    if rp_id and Decimal(qty) > 0:
        FillingIngredient.objects.update_or_create(
            filling=f,
            raw_product_id=rp_id,
            defaults={'quantity': qty, 'notes': notes},
        )
        messages.success(request, 'Ingrediente agregado.')
    return redirect('filling_edit', pk=f.pk)


@login_required
@require_POST
def filling_delete_ingredient(request, pk, ing_pk):
    ing = get_object_or_404(FillingIngredient, pk=ing_pk, filling_id=pk)
    ing.delete()
    messages.success(request, 'Ingrediente eliminado.')
    return redirect('filling_edit', pk=pk)


@login_required
@require_POST
def filling_edit_ingredient(request, pk, ing_pk):
    ing = get_object_or_404(FillingIngredient, pk=ing_pk, filling_id=pk)
    rp_id = request.POST.get('raw_product')
    qty = request.POST.get('quantity', '0')
    notes = request.POST.get('notes', '').strip()
    if rp_id and Decimal(qty) > 0:
        ing.raw_product_id = rp_id
        ing.quantity = qty
        ing.notes = notes
        ing.save()
        messages.success(request, 'Ingrediente actualizado.')
    return redirect('filling_edit', pk=pk)


# ── Topping CRUD ─────────────────────────────────────────────────────────────

@login_required
def topping_list(request):
    toppings = Topping.objects.order_by('name')
    search = request.GET.get('search', '')
    if search:
        toppings = toppings.filter(name__icontains=search)
    return render(request, 'control/topping_list.html', {'toppings': toppings, 'search': search})


@login_required
def topping_create(request):
    if request.method == 'POST':
        t = Topping(
            name=request.POST.get('name', '').strip(),
            description=request.POST.get('description', '').strip(),
            base_labor_per_portion=parse_decimal(request.POST.get('base_labor_per_portion', '0')),
            is_available=request.POST.get('is_available') == 'on',
        )
        t.save()
        messages.success(request, f'Cubierta "{t.name}" creada.')
        return redirect('topping_edit', pk=t.pk)
    return render(request, 'control/topping_form.html')


@login_required
def topping_edit(request, pk):
    t = get_object_or_404(Topping, pk=pk)
    ingredients = t.ingredients.select_related('raw_product').order_by('raw_product__name')
    raw_products = RawProduct.objects.order_by('name')
    if request.method == 'POST':
        t.name = request.POST.get('name', t.name)
        t.description = request.POST.get('description', t.description)
        t.base_labor_per_portion = parse_decimal(request.POST.get('base_labor_per_portion', '0'))
        t.is_available = request.POST.get('is_available') == 'on'
        t.save()
        messages.success(request, f'Cubierta "{t.name}" actualizada.')
        return redirect('topping_edit', pk=t.pk)
    return render(request, 'control/topping_form.html', {
        'object': t, 'ingredients': ingredients, 'raw_products': raw_products,
    })


@login_required
def topping_delete(request, pk):
    t = get_object_or_404(Topping, pk=pk)
    if request.method == 'POST':
        t.delete()
        messages.success(request, 'Cubierta eliminada.')
        return redirect('topping_list')
    return render(request, 'control/confirm_delete.html', {'object': t, 'cancel_url': 'topping_list'})


@login_required
@require_POST
def topping_add_ingredient(request, pk):
    t = get_object_or_404(Topping, pk=pk)
    rp_id = request.POST.get('raw_product')
    qty = request.POST.get('quantity', '0')
    notes = request.POST.get('notes', '').strip()
    if rp_id and Decimal(qty) > 0:
        ToppingIngredient.objects.update_or_create(
            topping=t,
            raw_product_id=rp_id,
            defaults={'quantity': qty, 'notes': notes},
        )
        messages.success(request, 'Ingrediente agregado.')
    return redirect('topping_edit', pk=t.pk)


@login_required
@require_POST
def topping_delete_ingredient(request, pk, ing_pk):
    ing = get_object_or_404(ToppingIngredient, pk=ing_pk, topping_id=pk)
    ing.delete()
    messages.success(request, 'Ingrediente eliminado.')
    return redirect('topping_edit', pk=pk)


@login_required
@require_POST
def topping_edit_ingredient(request, pk, ing_pk):
    ing = get_object_or_404(ToppingIngredient, pk=ing_pk, topping_id=pk)
    rp_id = request.POST.get('raw_product')
    qty = request.POST.get('quantity', '0')
    notes = request.POST.get('notes', '').strip()
    if rp_id and Decimal(qty) > 0:
        ing.raw_product_id = rp_id
        ing.quantity = qty
        ing.notes = notes
        ing.save()
        messages.success(request, 'Ingrediente actualizado.')
    return redirect('topping_edit', pk=pk)


# ── Brand CRUD ───────────────────────────────────────────────────────────────

@login_required
def brand_list(request):
    brands = Brand.objects.order_by('name')
    search = request.GET.get('search', '')
    if search:
        brands = brands.filter(name__icontains=search)
    return render(request, 'control/brand_list.html', {'brands': brands, 'search': search})


@login_required
def brand_create(request):
    if request.method == 'POST':
        b = Brand(
            name=request.POST.get('name', '').strip(),
            description=request.POST.get('description', '').strip(),
        )
        b.save()
        messages.success(request, f'Marca "{b.name}" creada.')
        return redirect('brand_list')
    return render(request, 'control/brand_form.html')


@login_required
def brand_edit(request, pk):
    b = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        b.name = request.POST.get('name', b.name)
        b.description = request.POST.get('description', b.description)
        b.save()
        messages.success(request, f'Marca "{b.name}" actualizada.')
        return redirect('brand_list')
    return render(request, 'control/brand_form.html', {'object': b})


@login_required
def brand_delete(request, pk):
    b = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        b.delete()
        messages.success(request, 'Marca eliminada.')
        return redirect('brand_list')
    return render(request, 'control/confirm_delete.html', {'object': b, 'cancel_url': 'brand_list'})


# ── EventTags CRUD ──────────────────────────────────────────────────────────

@login_required
def event_tag_list(request):
    tags = EventTag.objects.order_by('name')
    search = request.GET.get('search', '')
    if search:
        tags = tags.filter(name__icontains=search)
    return render(request, 'control/eventtag_list.html', {'tags': tags, 'search': search})


@login_required
def event_tag_create(request):
    if request.method == 'POST':
        t = EventTag(
            name=request.POST.get('name', '').strip(),
        )
        t.save()
        messages.success(request, f'Etiqueta "{t.name}" creada.')
        return redirect('event_tag_list')
    return render(request, 'control/eventtag_form.html')


@login_required
def event_tag_edit(request, pk):
    t = get_object_or_404(EventTag, pk=pk)
    if request.method == 'POST':
        t.name = request.POST.get('name', t.name)
        t.save()
        messages.success(request, f'Etiqueta "{t.name}" actualizada.')
        return redirect('event_tag_list')
    return render(request, 'control/eventtag_form.html', {'object': t})


@login_required
def event_tag_delete(request, pk):
    t = get_object_or_404(EventTag, pk=pk)
    if request.method == 'POST':
        t.delete()
        messages.success(request, 'Etiqueta eliminada.')
        return redirect('event_tag_list')
    return render(request, 'control/confirm_delete.html', {'object': t, 'cancel_url': 'event_tag_list'})


# ── Quick Create ─────────────────────────────────────────────────────────────

@login_required
def product_quick_create(request):
    breads = BaseBread.objects.filter(is_available=True)
    fillings = Filling.objects.filter(is_available=True)
    toppings = Topping.objects.filter(is_available=True)
    tiers = ComplexityTier.objects.all()
    clients = Client.objects.order_by('name')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'El nombre es obligatorio.')
            return render(request, 'control/product_quick_create.html', {
                'breads': breads, 'fillings': fillings, 'toppings': toppings,
                'tiers': tiers, 'clients': clients,
            })

        # 1. Get or create client
        client_id = request.POST.get('client')
        if client_id == '__new__':
            client = Client.objects.create(
                name=request.POST.get('new_client_name', '').strip(),
                email=request.POST.get('new_client_email', '').strip(),
                phone=request.POST.get('new_client_phone', '').strip(),
            )
        else:
            client = get_object_or_404(Client, pk=client_id)

        # 2. Create the quote (no product yet — only on sale)
        persons = int(request.POST.get('persons', 1))
        delivery_cost = parse_decimal(request.POST.get('delivery_cost', '0'))
        benefit = parse_decimal(request.POST.get('benefit', '50'))
        due_date_str = request.POST.get('due_date', '')
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else (datetime.now() + timedelta(days=15)).date()

        quote = Quote(
            client=client,
            name=name,
            persons=persons,
            design_notes=request.POST.get('design_notes', ''),
            delivery_cost=delivery_cost,
            show_delivery_on_pdf=request.POST.get('show_delivery_on_pdf') == 'on',
            benefit_percentage=benefit,
            due_date=due_date,
            status='sent',
        )
        if request.POST.get('base_bread'):
            quote.base_bread_id = int(request.POST['base_bread'])
        if request.POST.get('filling'):
            quote.filling_id = int(request.POST['filling'])
        if request.POST.get('topping'):
            quote.topping_id = int(request.POST['topping'])
        if request.POST.get('complexity_tier'):
            quote.complexity_tier_id = int(request.POST['complexity_tier'])
        quote.recalculate()
        quote.save()

        messages.success(request, f'✅ Cotización #{quote.id} creada para {client.name}.')
        return redirect('quote_download_pdf', pk=quote.pk)

    return render(request, 'control/product_quick_create.html', {
        'breads': breads, 'fillings': fillings, 'toppings': toppings,
        'tiers': tiers, 'clients': clients,
    })


# ── PDF Quote ────────────────────────────────────────────────────────────────

@login_required
def quote_download_pdf(request, pk):
    quote = get_object_or_404(Quote.objects.select_related('client', 'product'), pk=pk)
    html = render_to_string('control/quote_pdf.html', {'quote': quote})
    pdf = HTML(string=html).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="cotizacion_{quote.id}.pdf"'
    return response


# ── Order Workflow ─────────────────────────────────────────────────────────

@login_required
def order_approve(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        order.status = 'in_production'
        order.deadline = request.POST.get('deadline') or None
        order.save(update_fields=['status', 'deadline'])
        messages.success(request, f'Pedido #{order.id} aprobado a producción.')
    return redirect('order_list')


@login_required
def order_deliver(request, pk):
    order = get_object_or_404(Order, pk=pk)
    order.status = 'delivered'
    order.save(update_fields=['status'])
    messages.success(request, f'Pedido #{order.id} marcado como entregado.')
    return redirect('order_list')


@login_required
def order_pay(request, pk):
    order = get_object_or_404(Order, pk=pk)
    order.status = 'paid'
    order.save(update_fields=['status'])
    messages.success(request, f'Pedido #{order.id} marcado como pagado.')
    return redirect('order_list')


@login_required
def order_publish_gallery(request, pk):
    order = get_object_or_404(Order.objects.select_related('product'), pk=pk)
    product = order.product
    product.show_in_gallery = True
    product.save(update_fields=['show_in_gallery'])
    messages.success(request, f'✅ "{product.name}" publicado en la galería. Completa la información y foto.')
    return redirect('product_edit', pk=product.pk)


@login_required
def order_stock_check(request, pk):
    order = get_object_or_404(Order.objects.select_related('product', 'client'), pk=pk)
    shortages = order.check_stock_shortages()
    order.stock_verified = True
    order.save(update_fields=['stock_verified'])
    return render(request, 'control/order_stock_check.html', {
        'order': order,
        'shortages': shortages,
        'has_shortages': any(s['shortage'] > 0 for s in shortages),
    })


@login_required
def order_purchase_request_pdf(request, pk):
    order = get_object_or_404(Order.objects.select_related('product', 'client'), pk=pk)
    shortages = [s for s in order.check_stock_shortages() if s['shortage'] > 0]
    html = render_to_string('control/purchase_request_pdf.html', {'order': order, 'shortages': shortages})
    pdf = HTML(string=html).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="solicitud_compra_pedido_{order.id}.pdf"'
    return response


# ── Purchases CRUD ───────────────────────────────────────────────────────────

@login_required
def purchase_list(request):
    purchases = Purchase.objects.select_related('provider').order_by('-purchase_date')
    status_filter = request.GET.get('status')
    if status_filter:
        purchases = purchases.filter(status=status_filter)
    return render(request, 'control/purchase_list.html', {
        'purchases': purchases,
        'status_filter': status_filter,
        'status_choices': Purchase.STATUS_CHOICES,
    })


@login_required
def purchase_create(request):
    if request.method == 'POST':
        p = Purchase(
            provider_id=request.POST.get('provider'),
            status=request.POST.get('status', 'pending'),
            notes=request.POST.get('notes', ''),
        )
        p.save()
        # Save inline items
        raw_products = request.POST.getlist('raw_product[]')
        quantities = request.POST.getlist('quantity[]')
        unit_costs = request.POST.getlist('unit_cost[]')
        for rp_id, qty, cost in zip(raw_products, quantities, unit_costs):
            if rp_id and qty and cost:
                try:
                    PurchaseItem.objects.create(
                        purchase=p,
                        raw_product_id=int(rp_id),
                        quantity=Decimal(qty),
                        unit_cost=Decimal(cost),
                    )
                except Exception:
                    pass
        messages.success(request, f'Compra #{p.id} creada con {p.items.count()} artículo(s).')
        return redirect('purchase_list')
    return render(request, 'control/purchase_form.html', {
        'providers': Provider.objects.order_by('name'),
        'raw_products': RawProduct.objects.order_by('name'),
        'status_choices': Purchase.STATUS_CHOICES,
    })


@login_required
def purchase_edit(request, pk):
    p = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST':
        p.provider_id = request.POST.get('provider')
        p.status = request.POST.get('status', p.status)
        p.notes = request.POST.get('notes', '')
        p.save()
        # Replace inline items
        p.items.all().delete()
        raw_products = request.POST.getlist('raw_product[]')
        quantities = request.POST.getlist('quantity[]')
        unit_costs = request.POST.getlist('unit_cost[]')
        for rp_id, qty, cost in zip(raw_products, quantities, unit_costs):
            if rp_id and qty and cost:
                try:
                    PurchaseItem.objects.create(
                        purchase=p,
                        raw_product_id=int(rp_id),
                        quantity=Decimal(qty),
                        unit_cost=Decimal(cost),
                    )
                except Exception:
                    pass
        messages.success(request, f'Compra #{p.id} actualizada con {p.items.count()} artículo(s).')
        return redirect('purchase_list')
    return render(request, 'control/purchase_form.html', {
        'object': p,
        'providers': Provider.objects.order_by('name'),
        'raw_products': RawProduct.objects.order_by('name'),
        'status_choices': Purchase.STATUS_CHOICES,
        'items': p.items.select_related('raw_product').all(),
    })


@login_required
def purchase_delete(request, pk):
    p = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST':
        p.delete()
        messages.success(request, 'Compra eliminada.')
        return redirect('purchase_list')
    return render(request, 'control/confirm_delete.html', {'object': p, 'cancel_url': 'purchase_list'})


# ── Reports ──────────────────────────────────────────────────────────────────

@login_required
def reports_landing(request):
    return render(request, 'control/reports.html', {
        'total_products': Product.objects.count(),
        'total_clients': Client.objects.count(),
        'pending_orders': Order.objects.filter(status='pending').count(),
    })


@login_required
def inventory_report(request):
    products = Product.objects.all().order_by('name')
    inventory_data = []
    total_value = Decimal('0')
    for product in products:
        value = (product.price or Decimal('0')) * product.quantity_in_stock
        total_value += value
        inventory_data.append({'id': product.id, 'name': product.name, 'category': product.get_category_display(), 'quantity': product.quantity_in_stock, 'price': product.price, 'value': value})
    category = request.GET.get('category')
    if category:
        inventory_data = [p for p in inventory_data if Product.objects.get(id=p['id']).category == category]
        total_value = sum(Decimal(str(p['value'])) for p in inventory_data)
    return render(request, 'control/reports/inventory.html', {'inventory': inventory_data, 'total_value': total_value, 'categories': Product.CATEGORY_CHOICES, 'selected_category': category})


@login_required
def sales_report(request):
    orders = Order.objects.filter(status='completed').select_related('product', 'client').order_by('-order_date')
    date_filter = request.GET.get('date_filter', 'all')
    today = datetime.now().date()
    if date_filter == 'today':
        orders = orders.filter(order_date__date=today)
    elif date_filter == 'week':
        orders = orders.filter(order_date__date__gte=today - timedelta(days=7))
    elif date_filter == 'month':
        orders = orders.filter(order_date__date__gte=today - timedelta(days=30))
    total_sales = orders.aggregate(Sum('total_price'))['total_price__sum'] or Decimal('0')
    total_orders = orders.count()
    avg_order = total_sales / total_orders if total_orders > 0 else Decimal('0')
    best_sellers = orders.values('product__name').annotate(total_qty=Sum('persons'), total_revenue=Sum('total_price')).order_by('-total_revenue')[:5]
    return render(request, 'control/reports/sales.html', {'orders': orders[:20], 'total_sales': total_sales, 'total_orders': total_orders, 'avg_order': avg_order, 'best_sellers': best_sellers, 'date_filter': date_filter})


@login_required
def purchase_report(request):
    purchases = Purchase.objects.filter(status='received').prefetch_related('items__raw_product').order_by('-purchase_date')
    date_filter = request.GET.get('date_filter', 'all')
    today = datetime.now().date()
    if date_filter == 'today':
        purchases = purchases.filter(purchase_date__date=today)
    elif date_filter == 'week':
        purchases = purchases.filter(purchase_date__date__gte=today - timedelta(days=7))
    elif date_filter == 'month':
        purchases = purchases.filter(purchase_date__date__gte=today - timedelta(days=30))
    purchase_list = []
    total_spent = Decimal('0')
    for purchase in purchases:
        pt = purchase.total_cost
        total_spent += pt
        purchase_list.append({'id': purchase.id, 'provider': purchase.provider.name, 'total': pt, 'date': purchase.purchase_date, 'items_count': purchase.items.count()})
    return render(request, 'control/reports/purchases.html', {'purchases': purchase_list[:20], 'total_spent': total_spent, 'date_filter': date_filter})


@login_required
def sales_by_client_report(request):
    clients = Client.objects.annotate(total_orders=Count('orders', filter=Q(orders__status='completed')), total_spent=Sum('orders__total_price', filter=Q(orders__status='completed'))).filter(total_orders__gt=0).order_by('-total_spent')
    search = request.GET.get('search', '')
    if search:
        clients = clients.filter(name__icontains=search)
    return render(request, 'control/reports/sales_by_client.html', {'clients': clients, 'search': search})


@login_required
def raw_materials_report(request):
    raw_products = RawProduct.objects.all().order_by('name')
    provider = request.GET.get('provider')
    if provider:
        raw_products = raw_products.filter(provider_id=provider)
    from .models import Provider
    materials_data = []
    total_value = Decimal('0')
    low_stock_count = 0
    for material in raw_products:
        value = (material.cost_per_unit or Decimal('0')) * (material.quantity_in_stock or Decimal('0'))
        total_value += value
        is_low_stock = material.quantity_in_stock < material.reorder_level if material.quantity_in_stock else True
        if is_low_stock:
            low_stock_count += 1
        materials_data.append({'id': material.id, 'name': material.name, 'brand': material.brand.name if material.brand else '', 'provider': material.provider.name if material.provider else 'Sin proveedor', 'unit': material.unit, 'quantity': material.quantity_in_stock or 0, 'cost': material.cost_per_unit or Decimal('0'), 'value': value, 'reorder_level': material.reorder_level, 'is_low_stock': is_low_stock})
    return render(request, 'control/reports/raw_materials.html', {'materials': materials_data, 'total_value': total_value, 'low_stock_count': low_stock_count, 'providers': Provider.objects.all().order_by('name'), 'selected_provider': provider})


@login_required
def profits_report(request):
    date_filter = request.GET.get('date_filter', 'all')
    today = datetime.now().date()
    orders = Order.objects.filter(status='completed')
    if date_filter == 'today':
        orders = orders.filter(order_date__date=today)
    elif date_filter == 'week':
        orders = orders.filter(order_date__date__gte=today - timedelta(days=7))
    elif date_filter == 'month':
        orders = orders.filter(order_date__date__gte=today - timedelta(days=30))
    total_sales = orders.aggregate(Sum('total_price'))['total_price__sum'] or Decimal('0')
    from .models import PurchaseItem
    total_costs = PurchaseItem.objects.filter(purchase__status='received').aggregate(Sum('item_total'))['item_total__sum'] or Decimal('0')
    profit = total_sales - total_costs
    profit_margin = (profit / total_sales * 100) if total_sales > 0 else Decimal('0')
    from collections import defaultdict
    profitable_products = []
    for order in orders:
        product = order.product
        unit_profit = (product.price or Decimal('0')) - (product.cost or Decimal('0'))
        if unit_profit > 0:
            profitable_products.append({'name': product.name, 'quantity': order.persons, 'unit_price': product.price, 'unit_cost': product.cost, 'unit_profit': unit_profit, 'total_profit': unit_profit * order.persons})
    product_profits = defaultdict(lambda: {'quantity': 0, 'total_profit': 0, 'unit_price': Decimal('0'), 'unit_cost': Decimal('0')})
    for p in profitable_products:
        product_profits[p['name']]['quantity'] += p['quantity']
        product_profits[p['name']]['total_profit'] += p['total_profit']
        product_profits[p['name']]['unit_price'] = p['unit_price']
        product_profits[p['name']]['unit_cost'] = p['unit_cost']
    sorted_products = sorted([{'name': k, **v} for k, v in product_profits.items()], key=lambda x: x['total_profit'], reverse=True)[:5]
    return render(request, 'control/reports/profits.html', {'total_sales': total_sales, 'total_costs': total_costs, 'profit': profit, 'profit_margin': profit_margin, 'profitable_products': sorted_products, 'date_filter': date_filter})


@login_required
def price_compare(request):
    raw_products = RawProduct.objects.order_by('name', 'brand__name')
    selected_id = request.GET.get('raw_product')
    entries = []
    selected_rp = None
    if selected_id:
        try:
            selected_rp = RawProduct.objects.get(pk=selected_id)
            entries_list = list(ProviderCatalog.objects.filter(raw_product=selected_rp).select_related('provider').order_by('unit_price'))
            if entries_list:
                cheapest = entries_list[0].unit_price
                for e in entries_list:
                    e.diff_from_cheapest = e.unit_price - cheapest
            entries = entries_list
        except RawProduct.DoesNotExist:
            pass
    return render(request, 'control/price_compare.html', {'raw_products': raw_products, 'selected_id': int(selected_id) if selected_id else None, 'selected_rp': selected_rp, 'entries': entries})


# ── Order Calculator ─────────────────────────────────────────────────────────

@login_required
def order_calculator(request):
    products = Product.objects.filter(is_available=True).order_by('name')
    tiers = ComplexityTier.objects.all()
    clients = Client.objects.order_by('name')
    if request.method == 'POST':
        try:
            client = Client.objects.get(id=request.POST['client'])
            product = Product.objects.get(id=request.POST['product'], is_available=True)
            persons = int(request.POST['persons'])
        except (ValueError, KeyError, Client.DoesNotExist, Product.DoesNotExist):
            messages.error(request, 'Datos inválidos.')
            return render(request, 'control/order_calculator.html', {'products': products, 'tiers': tiers, 'clients': clients})
        original_tier = product.complexity_tier
        if request.POST.get('complexity_tier'):
            try:
                product.complexity_tier = ComplexityTier.objects.get(id=request.POST['complexity_tier'])
            except ComplexityTier.DoesNotExist:
                pass
        order = Order(client=client, product=product, persons=persons, design_notes=request.POST.get('design_notes', '').strip())
        order.save()
        product.complexity_tier = original_tier
        messages.success(request, f'Pedido #{order.id} creado.')
        return redirect('order_calculator')
    return render(request, 'control/order_calculator.html', {'products': products, 'tiers': tiers, 'clients': clients})


@login_required
def api_calculate_price(request):
    try:
        product = Product.objects.get(id=request.GET['product'], is_available=True)
        persons = int(request.GET.get('persons', 1))
        original_tier = product.complexity_tier
        tier_id = request.GET.get('complexity_tier')
        if tier_id:
            try:
                product.complexity_tier = ComplexityTier.objects.get(id=tier_id)
            except ComplexityTier.DoesNotExist:
                pass
        b = product.calculate_price_for(persons)
        product.complexity_tier = original_tier
        return JsonResponse({k: str(v) for k, v in b.items()})
    except Exception:
        return JsonResponse({'error': 'Parámetros inválidos'}, status=400)


# ── API: Calculate price from components (no product required) ─────────────

@login_required
def api_calculate_price_rapido(request):
    try:
        from decimal import Decimal
        persons = int(request.GET.get('persons', 1))
        tier_id = request.GET.get('complexity_tier')
        benefit = Decimal(request.GET.get('benefit', '50') or '50')

        base_bread_id = request.GET.get('base_bread')
        filling_id = request.GET.get('filling')
        topping_id = request.GET.get('topping')

        base_bread = get_object_or_404(BaseBread, pk=base_bread_id) if base_bread_id else None
        filling = get_object_or_404(Filling, pk=filling_id) if filling_id else None
        topping = get_object_or_404(Topping, pk=topping_id) if topping_id else None
        tier = get_object_or_404(ComplexityTier, pk=tier_id) if tier_id else None

        b = calculate_components_cost(base_bread, filling, topping, tier, persons, benefit)

        def _component(key, comp):
            if comp is None:
                return None
            ing_cost = comp.cost_per_portion()
            labor = comp.base_labor_per_portion or Decimal('0')
            details = []
            for ing in comp.ingredients.select_related('raw_product').order_by('raw_product__name'):
                details.append({
                    'name': ing.raw_product.name,
                    'qty': str(ing.quantity),
                    'unit': ing.raw_product.get_unit_display(),
                    'per_portion': str(ing.cost),
                    'total': str(ing.cost * persons),
                })
            return {
                'key': key,
                'name': comp.name,
                'ingredients_total': str(ing_cost * persons),
                'labor_total': str(labor * persons),
                'total': str((ing_cost + labor) * persons),
                'per_portion': str(ing_cost + labor),
                'details': details,
            }

        response = {
            'persons': str(persons),
            'ingredient_cost': str(b['ingredient_cost']),
            'labor_cost': str(b['labor_cost']),
            'design_surcharge': str(b['design_surcharge']),
            'benefit_amount': str(b['benefit_amount']),
            'benefit_percentage': str(benefit),
            'unit_price': str(b['unit_price']),
            'total': str(b['total']),
        }
        response['components'] = [
            _component('base_bread', base_bread),
            _component('filling', filling),
            _component('topping', topping),
        ]
        return JsonResponse(response)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ── Client Auth ──────────────────────────────────────────────────────────────

def register(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        phone = request.POST.get('phone', '').strip()
        if not name or not email or not password:
            messages.error(request, 'Todos los campos obligatorios.')
            return render(request, 'registration/register.html')
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Ya existe una cuenta con ese correo.')
            return render(request, 'registration/register.html')
        user = User.objects.create_user(username=email, email=email, password=password)
        user.first_name = name
        user.save()
        Client.objects.create(user=user, name=name, email=email, phone=phone)
        login(request, user)
        messages.success(request, f'¡Bienvenido {name}!')
        return redirect('control_dashboard')
    return render(request, 'registration/register.html')


def client_login(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=email, password=password)
        if user is None:
            user_lookup = User.objects.filter(email=email).first()
            if user_lookup:
                user = authenticate(request, username=user_lookup.username, password=password)
        if user is not None:
            login(request, user)
            return redirect(request.GET.get('next', 'control_dashboard'))
        else:
            messages.error(request, 'Correo o contraseña incorrectos.')
    return render(request, 'registration/login.html')


def client_logout(request):
    logout(request)
    return redirect('gallery')


# ── Client Quote Flow ─────────────────────────────────────────────────────────

@require_POST
def submit_inquiry(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_available=True)
    try:
        persons = int(request.POST.get('persons', 1))
    except ValueError:
        persons = 1

    if request.user.is_authenticated:
        client = Client.objects.filter(user=request.user).first()
        if client is None:
            messages.error(request, 'Tu cuenta no tiene perfil de cliente asociado.')
            return redirect('product_detail', product_id=product.id)
    else:
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        if not name or not email:
            messages.error(request, 'Nombre y correo son obligatorios para solicitar una cotización.')
            return redirect('product_detail', product_id=product.id)
        client = Client.objects.filter(email=email).first()
        if client is None:
            client = Client.objects.create(name=name, email=email, phone=phone)

    quote = Quote(
        client=client,
        product=product,
        name=product.name,
        persons=persons,
        design_notes=request.POST.get('design_notes', '').strip(),
        due_date=(datetime.now() + timedelta(days=15)).date(),
        status='draft',
    )
    quote.recalculate()
    quote.save()
    messages.success(request, '¡Cotización solicitada! La revisaremos y te contactaremos pronto.')
    return redirect('product_detail', product_id=product.id)


@login_required
def client_portal(request):
    client = Client.objects.filter(user=request.user).first()
    if client is None:
        messages.error(request, 'No tienes un perfil de cliente.')
        return redirect('gallery')
    quotes = Quote.objects.filter(client=client).select_related('product').order_by('-created_at')
    orders = Order.objects.filter(client=client).select_related('product').order_by('-order_date')
    return render(request, 'client_portal.html', {'client': client, 'quotes': quotes, 'orders': orders})


@login_required
@require_POST
def accept_quote(request, pk):
    quote = get_object_or_404(Quote, pk=pk, client__user=request.user)
    if quote.status == 'sent':
        quote.status = 'accepted'
        quote.save(update_fields=['status'])
        product = quote.ensure_product()
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
            notes=f"Convertido de Cotización #{quote.pk}",
        )
        Order.objects.filter(pk=order.pk).update(
            unit_price=quote.unit_price,
            design_surcharge=quote.design_surcharge,
            labor_cost=quote.labor_cost,
            total_price=quote.total_price,
        )
        messages.success(request, '✅ Cotización aceptada. Tu pedido ha sido creado.')
    return redirect('client_portal')


@login_required
@require_POST
def reject_quote(request, pk):
    quote = get_object_or_404(Quote, pk=pk, client__user=request.user)
    if quote.status == 'sent':
        quote.status = 'rejected'
        quote.save(update_fields=['status'])
        messages.success(request, 'Cotización rechazada.')
    return redirect('client_portal')


# ── Client Portal ────────────────────────────────────────────────────────────
