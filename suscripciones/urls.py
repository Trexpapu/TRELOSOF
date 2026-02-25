from django.urls import path
from . import views

urlpatterns = [
    path('metodo-pago/', views.agregar_metodo_pago, name='suscripcion-metodo-pago'),
    path('cancelar/', views.cancelar_suscripcion_view, name='suscripcion-cancelar'),
    path('registro/metodo-pago/', views.metodo_pago_registro, name='suscripcion-registro-pago'),
    path('cobrar/', views.ejecutar_cobro_manual, name='suscripcion-cobrar-manual'),
    path('historial/', views.historial_cobros, name='suscripcion-historial'),
    path('plan/', views.seleccionar_plan_view, name='suscripcion-seleccionar-plan'),
    path('cambiar-plan/', views.cambiar_plan_view, name='suscripcion-cambiar-plan'),
]
