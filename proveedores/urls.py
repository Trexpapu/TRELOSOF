from django.urls import path

from .views import *

urlpatterns = [
    path('proveedores', lista_proveedores, name='lista-proveedores'),
    path('crear/', crear_proveedor, name='crear-proveedor'),
    path('editar/<int:pk>/', editar_proveedor, name='editar-proveedor'),
    path('eliminar/<int:pk>/', eliminarProveedor, name='eliminar-proveedor'),
    
    # Cuenta Maestra
    path('cuenta-maestra/', ver_cuenta_maestra, name='ver-cuenta-maestra'),
    path('cuenta-maestra/crear/', crear_cuenta_maestra, name='crear-cuenta-maestra'),
    path('cuenta-maestra/editar/', editar_cuenta_maestra, name='editar-cuenta-maestra'),
]