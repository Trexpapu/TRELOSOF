
from django.urls import path
from .views import *
from django.views.generic import RedirectView

urlpatterns = [
    path('pago/<int:factura_id>/<str:fecha_str>/', pagar_factura, name='pagar-factura'),
    path('movimientos/', lista_movimientos, name='lista-movimientos'),
    path('editar/<int:movimiento_id>/', editar_pago_factura, name='editar-pago-factura'),
    path('eliminar/<int:movimiento_id>/', eliminar_pago_factura, name='eliminar-pago-factura'),
    path('pagar-masivo/', pagar_facturas_masivas, name='pagar-facturas-masivas'), 
    path('ajuste/', crear_ajuste_saldo, name='crear-ajuste-saldo'),
]
