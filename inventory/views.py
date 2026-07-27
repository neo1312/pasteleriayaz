from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum, Count, Q, F
from decimal import Decimal
from datetime import datetime, timedelta
import json
from .models import Product, Order, Purchase, RawProduct, Client, Quote, ProviderCatalog, ComplexityTier, Provider


def product_gallery(request):
    category = request.GET.get('category')
    if category:
        products = Product.objects.filter(is_available=True, category=category).order_by('name')
    else:
        products = Product.objects.filter(is_available=True).order_by('name')
    categories = Product.CATEGORY_CHOICES
    return render(request, 'inventory/gallery.html', {'products': products, 'categories': categories, 'selected_category': category})


def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_available=True)
    price_info = product.calculate_price_for(product.min_persons or 1)
    return render(request, 'inventory/product_detail.html', {'product': product, 'price_info': price_info})


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


# ── Quote maker ──────────────────────────────────────────────────────────────

@login_required
def quote_maker(request):
    if request.method == 'POST':
        try:
            product = Product.objects.get(id=request.POST['product'], is_available=True)
            client = Client.objects.get(id=request.POST['client'])
            persons = int(request.POST['persons'])
        except (ValueError, KeyError, Product.DoesNotExist, Client.DoesNotExist):
            return JsonResponse({'error': 'Datos inválidos'}, status=400)

        tier_id = request.POST.get('complexity_tier')
        original_tier = product.complexity_tier
        if tier_id:
            try:
                product.complexity_tier = ComplexityTier.objects.get(id=tier_id)
            except ComplexityTier.DoesNotExist:
                pass

        quote = Quote(
            client=client,
            product=product,
            persons=persons,
            design_notes=request.POST.get('design_notes', '').strip(),
            delivery_cost=Decimal(request.POST.get('delivery_cost', '0')),
            due_date=request.POST.get('due_date', None) or None,
        )
        quote.recalculate()
        quote.save()

        product.complexity_tier = original_tier

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'id': quote.id, 'status': 'ok'})

        messages.success(request, f'Cotización #{quote.id} creada.')
        return redirect('quotes_list')

    return render(request, 'control/quote_maker.html', {
        'products': Product.objects.filter(is_available=True).order_by('name'),
        'tiers': ComplexityTier.objects.all(),
        'clients': Client.objects.order_by('name'),
    })


@login_required
def quote_edit(request, pk):
    quote = get_object_or_404(Quote, pk=pk)
    if request.method == 'POST':
        try:
            quote.product = Product.objects.get(id=request.POST['product'])
            quote.client = Client.objects.get(id=request.POST['client'])
            quote.persons = int(request.POST['persons'])
            quote.design_notes = request.POST.get('design_notes', '').strip()
            quote.delivery_cost = Decimal(request.POST.get('delivery_cost', '0'))
            quote.due_date = request.POST.get('due_date', None) or None
            quote.recalculate()
            quote.save()
            messages.success(request, f'Cotización #{quote.id} actualizada.')
            return redirect('quotes_list')
        except (ValueError, KeyError):
            messages.error(request, 'Datos inválidos.')

    return render(request, 'control/quote_maker.html', {
        'products': Product.objects.filter(is_available=True).order_by('name'),
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
        Order.objects.create(
            client=quote.client,
            product=quote.product,
            persons=quote.persons,
            unit_price=quote.unit_price,
            design_notes=quote.design_notes,
            design_surcharge=quote.design_surcharge,
            labor_cost=quote.labor_cost,
            total_price=quote.total_price,
            notes=f"Convertido de Cotización #{quote.pk}",
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
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'El nombre es obligatorio.')
            return render(request, 'control/product_form.html', {'form': request.POST, 'tiers': tiers})
        product = Product(
            name=name,
            category=request.POST.get('category', 'other'),
            description=request.POST.get('description', ''),
            price=Decimal(request.POST.get('price', '0')),
            quantity_in_stock=Decimal(request.POST.get('quantity_in_stock', '0')),
            reorder_level=Decimal(request.POST.get('reorder_level', '10')),
            is_available=request.POST.get('is_available') == 'on',
        )
        if request.POST.get('complexity_tier'):
            product.complexity_tier_id = int(request.POST['complexity_tier'])
        if request.POST.get('base_labor_per_portion'):
            product.base_labor_per_portion = Decimal(request.POST['base_labor_per_portion'])
        if request.POST.get('min_persons'):
            product.min_persons = int(request.POST['min_persons'])
        if request.POST.get('max_persons'):
            product.max_persons = int(request.POST['max_persons'])
        product.save()
        messages.success(request, f'Producto "{product.name}" creado.')
        return redirect('product_list')
    return render(request, 'control/product_form.html', {'tiers': tiers})


@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    tiers = ComplexityTier.objects.all()
    if request.method == 'POST':
        product.name = request.POST.get('name', product.name)
        product.category = request.POST.get('category', product.category)
        product.description = request.POST.get('description', product.description)
        product.price = Decimal(request.POST.get('price', '0'))
        product.quantity_in_stock = Decimal(request.POST.get('quantity_in_stock', '0'))
        product.reorder_level = Decimal(request.POST.get('reorder_level', '10'))
        product.complexity_tier_id = request.POST.get('complexity_tier') or None
        product.base_labor_per_portion = Decimal(request.POST.get('base_labor_per_portion', '0'))
        product.min_persons = int(request.POST.get('min_persons', '1'))
        product.max_persons = int(request.POST.get('max_persons', '100'))
        product.is_available = request.POST.get('is_available') == 'on'
        product.save()
        messages.success(request, f'Producto "{product.name}" actualizado.')
        return redirect('product_list')
    return render(request, 'control/product_form.html', {'form': product, 'object': product, 'tiers': tiers})


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
        materials = materials.filter(Q(name__icontains=search) | Q(brand__icontains=search))
    return render(request, 'control/rawproduct_list.html', {'materials': materials, 'search': search})


@login_required
def rawproduct_create(request):
    providers = Provider.objects.order_by('name')
    if request.method == 'POST':
        rp = RawProduct(
            name=request.POST.get('name', '').strip(),
            brand=request.POST.get('brand', '').strip(),
            unit=request.POST.get('unit', 'kg'),
            cost_per_unit=Decimal(request.POST.get('cost_per_unit', '0')),
            quantity_in_stock=Decimal(request.POST.get('quantity_in_stock', '0')),
            reorder_level=Decimal(request.POST.get('reorder_level', '10')),
            provider_id=request.POST.get('provider') or None,
        )
        rp.save()
        messages.success(request, f'Insumo "{rp.name}" creado.')
        return redirect('rawproduct_list')
    return render(request, 'control/rawproduct_form.html', {
        'providers': providers,
        'units': RawProduct.UNIT_CHOICES,
    })


@login_required
def rawproduct_edit(request, pk):
    rp = get_object_or_404(RawProduct, pk=pk)
    providers = Provider.objects.order_by('name')
    if request.method == 'POST':
        rp.name = request.POST.get('name', rp.name)
        rp.brand = request.POST.get('brand', rp.brand)
        rp.unit = request.POST.get('unit', rp.unit)
        rp.cost_per_unit = Decimal(request.POST.get('cost_per_unit', '0'))
        rp.quantity_in_stock = Decimal(request.POST.get('quantity_in_stock', '0'))
        rp.reorder_level = Decimal(request.POST.get('reorder_level', '10'))
        rp.provider_id = request.POST.get('provider') or None
        rp.save()
        messages.success(request, f'Insumo "{rp.name}" actualizado.')
        return redirect('rawproduct_list')
    return render(request, 'control/rawproduct_form.html', {'object': rp, 'providers': providers, 'units': RawProduct.UNIT_CHOICES})


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
        materials_data.append({'id': material.id, 'name': material.name, 'brand': material.brand, 'provider': material.provider.name if material.provider else 'Sin proveedor', 'unit': material.unit, 'quantity': material.quantity_in_stock or 0, 'cost': material.cost_per_unit or Decimal('0'), 'value': value, 'reorder_level': material.reorder_level, 'is_low_stock': is_low_stock})
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
    raw_products = RawProduct.objects.order_by('name', 'brand')
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
        return redirect('client_portal')
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
            return redirect(request.GET.get('next', 'client_portal'))
        else:
            messages.error(request, 'Correo o contraseña incorrectos.')
    return render(request, 'registration/login.html')


def client_logout(request):
    logout(request)
    return redirect('gallery')


# ── Client Portal ────────────────────────────────────────────────────────────

@login_required
def client_portal(request):
    try:
        client = request.user.client
    except Client.DoesNotExist:
        messages.error(request, 'No tienes un perfil de cliente asociado.')
        return redirect('gallery')
    return render(request, 'client_portal.html', {
        'client': client,
        'quotes': Quote.objects.filter(client=client).select_related('product').order_by('-created_at'),
        'orders': Order.objects.filter(client=client).select_related('product').order_by('-order_date'),
    })


@login_required
def submit_inquiry(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_available=True)
    if request.method == 'POST':
        try:
            persons = int(request.POST.get('persons', 0))
        except (TypeError, ValueError):
            messages.error(request, 'Número inválido.')
            return redirect('product_detail', product_id=product.id)
        if persons < (product.min_persons or 1):
            messages.error(request, f'Mínimo {product.min_persons or 1} persona(s).')
            return redirect('product_detail', product_id=product.id)
        if product.max_persons and persons > product.max_persons:
            messages.error(request, f'Máximo {product.max_persons} persona(s).')
            return redirect('product_detail', product_id=product.id)
        # Resolve client
        if request.user.is_authenticated:
            try:
                client = request.user.client
            except Client.DoesNotExist:
                messages.error(request, 'Completa tu registro como cliente primero.')
                return redirect('register')
        else:
            email = request.POST.get('email', '').strip().lower()
            name = request.POST.get('name', '').strip()
            phone = request.POST.get('phone', '').strip()
            if not email:
                messages.error(request, 'Correo electrónico requerido.')
                return redirect('product_detail', product_id=product.id)
            client_qs = Client.objects.filter(email=email)
            if client_qs.exists():
                client = client_qs.first()
            else:
                client = Client.objects.create(name=name or email, email=email, phone=phone)
        quote = Quote(client=client, product=product, persons=persons, design_notes=request.POST.get('design_notes', '').strip(), status='draft')
        quote.recalculate()
        quote.save()
        messages.success(request, '¡Cotización solicitada! Te contactaremos pronto.')
        if request.user.is_authenticated:
            return redirect('client_portal')
        return redirect('product_detail', product_id=product.id)
    return redirect('product_detail', product_id=product.id)


@login_required
def accept_quote(request, quote_id):
    try:
        client = request.user.client
        quote = Quote.objects.get(id=quote_id, client=client)
    except (Client.DoesNotExist, Quote.DoesNotExist):
        messages.error(request, 'Cotización no encontrada.')
        return redirect('client_portal')
    if quote.status != 'sent':
        messages.error(request, 'Esta cotización no está disponible.')
        return redirect('client_portal')
    quote.status = 'accepted'
    quote.save(update_fields=['status'])
    Order.objects.create(client=client, product=quote.product, persons=quote.persons, unit_price=quote.unit_price, design_notes=quote.design_notes, design_surcharge=quote.design_surcharge, labor_cost=quote.labor_cost, total_price=quote.total_price, notes=f"Convertido de Cotización #{quote.pk}")
    messages.success(request, '¡Cotización aceptada! Pedido creado.')
    return redirect('client_portal')


@login_required
def reject_quote(request, quote_id):
    try:
        client = request.user.client
        quote = Quote.objects.get(id=quote_id, client=client)
    except (Client.DoesNotExist, Quote.DoesNotExist):
        messages.error(request, 'Cotización no encontrada.')
        return redirect('client_portal')
    if quote.status != 'sent':
        messages.error(request, 'Esta cotización no está disponible.')
        return redirect('client_portal')
    quote.status = 'rejected'
    quote.save(update_fields=['status'])
    messages.info(request, 'Cotización rechazada.')
    return redirect('client_portal')
