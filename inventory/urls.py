from django.urls import path
from . import views

urlpatterns = [
    # Home — public gallery
    path('', views.product_gallery, name='gallery'),

    # Dashboard — owner panel (login required)
    path('dash/', views.control_dashboard, name='control_dashboard'),
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),

    # Productos
    path('productos/', views.product_list, name='product_list'),
    path('productos/nuevo/', views.product_create, name='product_create'),
    path('productos/<int:pk>/editar/', views.product_edit, name='product_edit'),
    path('productos/<int:pk>/eliminar/', views.product_delete, name='product_delete'),

    # Clientes
    path('clientes/', views.client_list, name='client_list'),
    path('clientes/nuevo/', views.client_create, name='client_create'),
    path('clientes/<int:pk>/editar/', views.client_edit, name='client_edit'),
    path('clientes/<int:pk>/eliminar/', views.client_delete, name='client_delete'),

    # Pedidos
    path('pedidos/', views.order_list, name='order_list'),
    path('pedidos/<int:pk>/editar/', views.order_edit, name='order_edit'),
    path('pedidos/<int:pk>/eliminar/', views.order_delete, name='order_delete'),

    # Materias primas
    path('materias-primas/', views.rawproduct_list, name='rawproduct_list'),
    path('materias-primas/nuevo/', views.rawproduct_create, name='rawproduct_create'),
    path('materias-primas/<int:pk>/editar/', views.rawproduct_edit, name='rawproduct_edit'),
    path('materias-primas/<int:pk>/eliminar/', views.rawproduct_delete, name='rawproduct_delete'),

    # Proveedores
    path('proveedores/', views.provider_list, name='provider_list'),
    path('proveedores/nuevo/', views.provider_create, name='provider_create'),
    path('proveedores/<int:pk>/editar/', views.provider_edit, name='provider_edit'),
    path('proveedores/<int:pk>/eliminar/', views.provider_delete, name='provider_delete'),

    # Niveles de Complejidad
    path('niveles-complejidad/', views.complexity_tier_list, name='complexity_tier_list'),
    path('niveles-complejidad/nuevo/', views.complexity_tier_create, name='complexity_tier_create'),
    path('niveles-complejidad/<int:pk>/editar/', views.complexity_tier_edit, name='complexity_tier_edit'),
    path('niveles-complejidad/<int:pk>/eliminar/', views.complexity_tier_delete, name='complexity_tier_delete'),

    # Bases de Pastel
    path('bases/', views.base_bread_list, name='base_bread_list'),
    path('bases/nueva/', views.base_bread_create, name='base_bread_create'),
    path('bases/<int:pk>/editar/', views.base_bread_edit, name='base_bread_edit'),
    path('bases/<int:pk>/eliminar/', views.base_bread_delete, name='base_bread_delete'),

    # Rellenos
    path('rellenos/', views.filling_list, name='filling_list'),
    path('rellenos/nuevo/', views.filling_create, name='filling_create'),
    path('rellenos/<int:pk>/editar/', views.filling_edit, name='filling_edit'),
    path('rellenos/<int:pk>/eliminar/', views.filling_delete, name='filling_delete'),

    # Cubiertas
    path('cubiertas/', views.topping_list, name='topping_list'),
    path('cubiertas/nueva/', views.topping_create, name='topping_create'),
    path('cubiertas/<int:pk>/editar/', views.topping_edit, name='topping_edit'),
    path('cubiertas/<int:pk>/eliminar/', views.topping_delete, name='topping_delete'),

    # Marcas
    path('marcas/', views.brand_list, name='brand_list'),
    path('marcas/nueva/', views.brand_create, name='brand_create'),
    path('marcas/<int:pk>/editar/', views.brand_edit, name='brand_edit'),
    path('marcas/<int:pk>/eliminar/', views.brand_delete, name='brand_delete'),

    # Compras
    path('compras/', views.purchase_list, name='purchase_list'),
    path('compras/nueva/', views.purchase_create, name='purchase_create'),
    path('compras/<int:pk>/editar/', views.purchase_edit, name='purchase_edit'),
    path('compras/<int:pk>/eliminar/', views.purchase_delete, name='purchase_delete'),

    # Cotizaciones (admin)
    path('cotizaciones/', views.quotes_list, name='quotes_list'),
    path('cotizaciones/nueva/', views.quote_maker, name='quote_maker'),
    path('cotizaciones/<int:pk>/editar/', views.quote_edit, name='quote_edit'),
    path('cotizaciones/<int:pk>/eliminar/', views.quote_delete, name='quote_delete'),
    path('cotizaciones/<int:pk>/enviar/', views.quote_send, name='quote_send'),
    path('cotizaciones/<int:pk>/aprobar/', views.quote_approve, name='quote_approve'),

    # Reportes
    path('reportes/', views.reports_landing, name='admin_dashboard'),
    path('reportes/inventario/', views.inventory_report, name='inventory_report'),
    path('reportes/ventas/', views.sales_report, name='sales_report'),
    path('reportes/compras/', views.purchase_report, name='purchase_report'),
    path('reportes/ventas-por-cliente/', views.sales_by_client_report, name='sales_by_client_report'),
    path('reportes/materias-primas/', views.raw_materials_report, name='raw_materials_report'),
    path('reportes/utilidades/', views.profits_report, name='profits_report'),

    # Comparar precios
    path('comparar-precios/', views.price_compare, name='price_compare'),

    # API
    path('api/calcular-precio/', views.api_calculate_price, name='api_calculate_price'),

    # Cliente — auth
    path('registro/', views.register, name='register'),
    path('ingresar/', views.client_login, name='login'),
    path('salir/', views.client_logout, name='logout'),
]
