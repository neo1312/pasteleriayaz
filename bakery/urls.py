"""
URL configuration for bakery project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from inventory import views

urlpatterns = [
    # Reportes (antes de admin para que no sean capturados por el patrón comodín)
    path('reportes/', views.admin_dashboard, name='admin_dashboard'),
    path('reportes/inventario/', views.inventory_report, name='inventory_report'),
    path('reportes/ventas/', views.sales_report, name='sales_report'),
    path('reportes/compras/', views.purchase_report, name='purchase_report'),
    path('reportes/ventas-por-cliente/', views.sales_by_client_report, name='sales_by_client_report'),
    path('reportes/materias-primas/', views.raw_materials_report, name='raw_materials_report'),
    path('reportes/utilidades/', views.profits_report, name='profits_report'),
    
    # Admin
    path('admin/', admin.site.urls),
    
    # Galería pública
    path('', include('inventory.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
