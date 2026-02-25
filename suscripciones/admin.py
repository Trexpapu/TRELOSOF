from django.contrib import admin
from .models import Suscripcion, HistorialCobro


@admin.register(Suscripcion)
class SuscripcionAdmin(admin.ModelAdmin):
    list_display = ['organizacion', 'estado', 'trial_fin', 'proximo_cobro', 'card_brand', 'card_last4', 'precio_mensual']
    list_filter = ['estado']
    search_fields = ['organizacion__nombre']
    readonly_fields = ['created_at', 'updated_at', 'stripe_customer_id', 'stripe_subscription_id']


@admin.register(HistorialCobro)
class HistorialCobroAdmin(admin.ModelAdmin):
    list_display = ['suscripcion', 'fecha', 'monto', 'resultado', 'stripe_charge_id']
    list_filter = ['resultado']
    readonly_fields = ['fecha', 'stripe_charge_id']
