from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F
from decimal import Decimal
from datetime import datetime, timedelta
from .models import Product, Order, Purchase, RawProduct, Client

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
    return render(request, 'inventory/product_detail.html', {'product': product})


@login_required
def admin_dashboard(request):
    """Dashboard principal del admin con acceso a reportes"""
    # Estadísticas rápidas
    total_products = Product.objects.count()
    total_clients = Client.objects.count()
    pending_orders = Order.objects.filter(status='pending').count()
    
    context = {
        'total_products': total_products,
        'total_clients': total_clients,
        'pending_orders': pending_orders,
    }
    return render(request, 'admin/dashboard.html', context)


@login_required
def inventory_report(request):
    """Reporte de inventario - valor actual de productos"""
    products = Product.objects.all().order_by('name')
    
    # Calcular valor de inventario
    inventory_data = []
    total_value = Decimal('0')
    
    for product in products:
        value = (product.price or Decimal('0')) * product.quantity_in_stock
        total_value += value
        inventory_data.append({
            'id': product.id,
            'name': product.name,
            'category': product.get_category_display(),
            'quantity': product.quantity_in_stock,
            'price': product.price,
            'value': value,
        })
    
    # Filtro por categoría
    category = request.GET.get('category')
    if category:
        inventory_data = [p for p in inventory_data if Product.objects.get(id=p['id']).category == category]
        total_value = sum(Decimal(str(p['value'])) for p in inventory_data)
    
    categories = Product.CATEGORY_CHOICES
    
    context = {
        'inventory': inventory_data,
        'total_value': total_value,
        'categories': categories,
        'selected_category': category,
    }
    return render(request, 'admin/reports/inventory.html', context)


@login_required
def sales_report(request):
    """Reporte de ventas"""
    orders = Order.objects.filter(status='completed').select_related('product', 'client').order_by('-order_date')
    
    # Filtros
    date_filter = request.GET.get('date_filter', 'all')
    today = datetime.now().date()
    
    if date_filter == 'today':
        orders = orders.filter(order_date__date=today)
    elif date_filter == 'week':
        week_ago = today - timedelta(days=7)
        orders = orders.filter(order_date__date__gte=week_ago)
    elif date_filter == 'month':
        month_ago = today - timedelta(days=30)
        orders = orders.filter(order_date__date__gte=month_ago)
    
    # Calculales totales
    total_sales = orders.aggregate(Sum('total_price'))['total_price__sum'] or Decimal('0')
    total_orders = orders.count()
    avg_order = total_sales / total_orders if total_orders > 0 else Decimal('0')
    
    # Productos más vendidos
    best_sellers = (
        orders.values('product__name')
        .annotate(total_qty=Sum('quantity'), total_revenue=Sum('total_price'))
        .order_by('-total_revenue')[:5]
    )
    
    context = {
        'orders': orders[:20],
        'total_sales': total_sales,
        'total_orders': total_orders,
        'avg_order': avg_order,
        'best_sellers': best_sellers,
        'date_filter': date_filter,
    }
    return render(request, 'admin/reports/sales.html', context)


@login_required
def purchase_report(request):
    """Reporte de compras"""
    purchases = Purchase.objects.filter(status='received').prefetch_related('items__raw_product').order_by('-purchase_date')
    
    # Filtro de fecha
    date_filter = request.GET.get('date_filter', 'all')
    today = datetime.now().date()
    
    if date_filter == 'today':
        purchases = purchases.filter(purchase_date__date=today)
    elif date_filter == 'week':
        week_ago = today - timedelta(days=7)
        purchases = purchases.filter(purchase_date__date__gte=week_ago)
    elif date_filter == 'month':
        month_ago = today - timedelta(days=30)
        purchases = purchases.filter(purchase_date__date__gte=month_ago)
    
    # Totales
    total_spent = Decimal('0')
    purchase_list = []
    
    for purchase in purchases:
        purchase_total = purchase.total_cost
        total_spent += purchase_total
        purchase_list.append({
            'id': purchase.id,
            'provider': purchase.provider.name,
            'total': purchase_total,
            'date': purchase.purchase_date,
            'items_count': purchase.items.count(),
        })
    
    context = {
        'purchases': purchase_list[:20],
        'total_spent': total_spent,
        'date_filter': date_filter,
    }
    return render(request, 'admin/reports/purchases.html', context)


@login_required
def sales_by_client_report(request):
    """Reporte de ventas por cliente"""
    clients = Client.objects.annotate(
        total_orders=Count('orders', filter=Q(orders__status='completed')),
        total_spent=Sum('orders__total_price', filter=Q(orders__status='completed')),
    ).filter(total_orders__gt=0).order_by('-total_spent')
    
    # Filtro por búsqueda
    search = request.GET.get('search', '')
    if search:
        clients = clients.filter(name__icontains=search)
    
    context = {
        'clients': clients,
        'search': search,
    }
    return render(request, 'admin/reports/sales_by_client.html', context)


@login_required
def raw_materials_report(request):
    """Reporte de materias primas - inventario de componentes"""
    raw_products = RawProduct.objects.all().order_by('name')
    
    # Filtro por proveedor
    provider = request.GET.get('provider')
    if provider:
        raw_products = raw_products.filter(provider_id=provider)
    
    # Calcular datos
    materials_data = []
    total_value = Decimal('0')
    low_stock_count = 0
    
    for material in raw_products:
        value = (material.cost_per_unit or Decimal('0')) * (material.quantity_in_stock or Decimal('0'))
        total_value += value
        
        is_low_stock = material.quantity_in_stock < material.reorder_level if material.quantity_in_stock else True
        if is_low_stock:
            low_stock_count += 1
        
        materials_data.append({
            'id': material.id,
            'name': material.name,
            'brand': material.brand,
            'provider': material.provider.name if material.provider else 'Sin proveedor',
            'unit': material.unit,
            'quantity': material.quantity_in_stock or 0,
            'cost': material.cost_per_unit or Decimal('0'),
            'value': value,
            'reorder_level': material.reorder_level,
            'is_low_stock': is_low_stock,
        })
    
    # Obtener lista de proveedores
    from .models import Provider
    providers = Provider.objects.all().order_by('name')
    
    context = {
        'materials': materials_data,
        'total_value': total_value,
        'low_stock_count': low_stock_count,
        'providers': providers,
        'selected_provider': provider,
    }
    return render(request, 'admin/reports/raw_materials.html', context)


@login_required
def profits_report(request):
    """Reporte de utilidades - ganancias vs costos"""
    # Filtro de período
    date_filter = request.GET.get('date_filter', 'all')
    today = datetime.now().date()
    
    orders = Order.objects.filter(status='completed')
    
    if date_filter == 'today':
        orders = orders.filter(order_date__date=today)
    elif date_filter == 'week':
        week_ago = today - timedelta(days=7)
        orders = orders.filter(order_date__date__gte=week_ago)
    elif date_filter == 'month':
        month_ago = today - timedelta(days=30)
        orders = orders.filter(order_date__date__gte=month_ago)
    
    # Calcular totales de ventas
    total_sales = orders.aggregate(Sum('total_price'))['total_price__sum'] or Decimal('0')
    
    # Calcular total de costos de compras recibidas
    from .models import PurchaseItem
    purchase_items = PurchaseItem.objects.filter(purchase__status='received')
    total_costs = purchase_items.aggregate(Sum('item_total'))['item_total__sum'] or Decimal('0')
    
    # Calcular utilidad
    profit = total_sales - total_costs
    profit_margin = (profit / total_sales * 100) if total_sales > 0 else Decimal('0')
    
    # Productos más rentables (ganancia = price - cost por unidad)
    profitable_products = []
    for order in orders:
        product = order.product
        unit_profit = (product.price or Decimal('0')) - (product.cost or Decimal('0'))
        if unit_profit > 0:
            profitable_products.append({
                'name': product.name,
                'quantity': order.quantity,
                'unit_price': product.price,
                'unit_cost': product.cost,
                'unit_profit': unit_profit,
                'total_profit': unit_profit * order.quantity,
            })
    
    # Agrupar por producto y sumar
    from collections import defaultdict
    product_profits = defaultdict(lambda: {'quantity': 0, 'total_profit': 0, 'unit_price': Decimal('0'), 'unit_cost': Decimal('0')})
    
    for p in profitable_products:
        product_profits[p['name']]['quantity'] += p['quantity']
        product_profits[p['name']]['total_profit'] += p['total_profit']
        product_profits[p['name']]['unit_price'] = p['unit_price']
        product_profits[p['name']]['unit_cost'] = p['unit_cost']
    
    # Ordenar por ganancia
    sorted_products = sorted(
        [{'name': k, **v} for k, v in product_profits.items()],
        key=lambda x: x['total_profit'],
        reverse=True
    )[:5]
    
    context = {
        'total_sales': total_sales,
        'total_costs': total_costs,
        'profit': profit,
        'profit_margin': profit_margin,
        'profitable_products': sorted_products,
        'date_filter': date_filter,
    }
    return render(request, 'admin/reports/profits.html', context)
