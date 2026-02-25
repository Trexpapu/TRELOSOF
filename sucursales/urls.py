
from django.urls import path
from .views import (
    lista_sucursales, crear_sucursal, editar_sucursal, eliminar_sucursal,
    lista_ventas, crear_venta, editar_venta, eliminar_venta,
)

urlpatterns = [
    # Sucursales
    path('sucursales/', lista_sucursales, name='lista-sucursales'),
    path('crear/', crear_sucursal, name='crear-sucursal'),
    path('editar/<int:sucursal_id>/', editar_sucursal, name='editar-sucursal'),
    path('eliminar/<int:sucursal_id>/', eliminar_sucursal, name='eliminar-sucursal'),
    # Ventas / Ingresos
    path('ventas/', lista_ventas, name='lista-ventas'),
    path('crear-venta/<str:fecha_str>/', crear_venta, name='crear-venta'),
    path('editar-venta/<int:venta_id>/<str:fecha_str>/', editar_venta, name='editar-venta'),
    path('eliminar-venta/<int:venta_id>/<str:fecha_str>/', eliminar_venta, name='eliminar-venta'),
]
