from django.urls import path

from .views import crear_factura, editar_factura, eliminar_factura, lista_facturas

urlpatterns = [
    path('facturas/', lista_facturas, name='lista-facturas'),
    path('crear/<str:fecha_str>/', crear_factura, name='crear-factura'),
    path('editar/<int:factura_id>/<str:fecha_str>/', editar_factura, name='editar-factura'),
    path('eliminar/<int:factura_id>/<str:fecha_str>/', eliminar_factura, name='eliminar-factura'),
]