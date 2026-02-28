from django.urls import path
from . import views

urlpatterns = [
    path('cancelar/', views.cancelar_suscripcion_view, name='suscripcion-cancelar'),
    path('historial/', views.historial_cobros, name='suscripcion-historial'),
    path('plan/', views.seleccionar_plan_view, name='suscripcion-seleccionar-plan'),
    path('cambiar-plan/', views.cambiar_plan_view, name='suscripcion-cambiar-plan'),
    # ── Stripe Checkout ────────────────────────────────────────────────────────
    path('checkout/<str:plan>/', views.crear_checkout_session, name='suscripcion-checkout'),
    path('checkout/exito/', views.checkout_exitoso, name='suscripcion-checkout-exito'),
    # ── Stripe Webhook (sin CSRF, sin login) ──────────────────────────────────
    path('webhook/', views.stripe_webhook, name='suscripcion-webhook'),
]
