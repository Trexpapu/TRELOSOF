from django.db import models
from django.utils import timezone
from datetime import timedelta


class Suscripcion(models.Model):
    """
    Suscripción mensual por organización.
    El ciclo de vida es:
      TRIAL → ACTIVA (cobro mensual) → CANCELADA

    Lógica de meses anticipados:
      proximo_cobro siempre apunta al fin del último período pagado.
      Si proximo_cobro > hoy → el cliente tiene meses de crédito.
      El cron solo cobra cuando proximo_cobro <= hoy.
    """

    ESTADOS = [
        ('TRIAL', 'Período de Prueba'),
        ('ACTIVA', 'Activa'),
        ('VENCIDA', 'Vencida'),
        ('CANCELADA', 'Cancelada'),
    ]

    PLANES = [
        ('BASICO', 'Plan Básico'),
        ('PRO',    'Plan Pro'),
    ]

    organizacion = models.OneToOneField(
        'users.Organizacion',
        on_delete=models.CASCADE,
        related_name='suscripcion'
    )

    # ── Estado ──────────────────────────────────────────────────────────────────────────────
    estado = models.CharField(max_length=20, choices=ESTADOS, default='TRIAL')

    # ── Plan ─────────────────────────────────────────────────────────────────────────────────
    plan           = models.CharField(max_length=10, choices=PLANES, null=True, blank=True)

    # ── Fechas ──────────────────────────────────────────────────────────────────────────────
    fecha_inicio = models.DateTimeField(default=timezone.now)
    trial_fin    = models.DateTimeField(null=True, blank=True)   # 2 semanas desde registro
    proximo_cobro = models.DateTimeField(null=True, blank=True)   # Fin del último período pagado

    # ── Stripe IDs ──────────────────────────────────────────────────────────────────────
    stripe_customer_id    = models.CharField(max_length=120, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=120, blank=True, null=True)
    stripe_payment_method_id = models.CharField(max_length=120, blank=True, null=True)

    # ── Tarjeta (solo datos de display, nunca datos sensibles) ─────────────────────
    card_brand    = models.CharField(max_length=20, blank=True, null=True)   # visa, mastercard…
    card_last4    = models.CharField(max_length=4, blank=True, null=True)
    card_exp_month = models.PositiveSmallIntegerField(null=True, blank=True)
    card_exp_year  = models.PositiveSmallIntegerField(null=True, blank=True)

    # ── Precio mensual (en MXN) ───────────────────────────────────────────────────────────
    precio_mensual = models.DecimalField(max_digits=10, decimal_places=2, default=199.00)

    # ── Auditoría ─────────────────────────────────────────────────────────────────────────────
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)


    class Meta:
        verbose_name = 'Suscripción'
        verbose_name_plural = 'Suscripciones'

    def __str__(self):
        return f"{self.organizacion.nombre} – {self.get_estado_display()}"

    # ── Helpers ───────────────────────────────────────────────────────────────
    @property
    def en_trial(self):
        if self.estado == 'TRIAL' and self.trial_fin:
            return timezone.now() <= self.trial_fin
        return False

    @property
    def trial_dias_restantes(self):
        if self.en_trial:
            delta = self.trial_fin - timezone.now()
            return max(delta.days, 0)
        return 0

    @property
    def tiene_metodo_pago(self):
        return bool(self.stripe_payment_method_id)

    @property
    def activa(self):
        return self.estado in ('TRIAL', 'ACTIVA')

    @property
    def dias_cubiertos(self):
        """
        Cuántos días de crédito tiene el cliente más allá de hoy.
        0 si proximo_cobro ya venció o no existe.
        """
        if self.proximo_cobro and self.proximo_cobro > timezone.now():
            return max((self.proximo_cobro - timezone.now()).days, 0)
        return 0

    @property
    def max_usuarios(self):
        """Límite de usuarios activos según el plan actual."""
        from django.conf import settings
        if self.plan == 'PRO':
            return settings.PLAN_PRO_MAX_USUARIOS
        return settings.PLAN_BASICO_MAX_USUARIOS   # BASICO o None (trial sin plan)

    @property
    def precio_plan(self):
        """Precio mensual según el plan activo en la BD."""
        from django.conf import settings
        if self.plan == 'PRO':
            return settings.PLAN_PRO_PRECIO
        return settings.PLAN_BASICO_PRECIO

    @property
    def plan_display(self):
        return dict(self.PLANES).get(self.plan, '—')



class HistorialCobro(models.Model):
    """
    Registro inmutable de cada intento de cobro.
    """
    RESULTADOS = [
        ('EXITOSO', 'Exitoso'),
        ('FALLIDO', 'Fallido'),
        ('PENDIENTE', 'Pendiente'),
        ('REEMBOLSADO', 'Reembolsado'),
    ]

    suscripcion    = models.ForeignKey(Suscripcion, on_delete=models.CASCADE, related_name='cobros')
    fecha          = models.DateTimeField(default=timezone.now)
    monto          = models.DecimalField(max_digits=10, decimal_places=2)
    resultado      = models.CharField(max_length=20, choices=RESULTADOS)
    stripe_charge_id = models.CharField(max_length=120, blank=True, null=True)
    descripcion    = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'Historial de Cobro'
        verbose_name_plural = 'Historial de Cobros'
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.suscripcion.organizacion.nombre} | {self.fecha:%d/%m/%Y} | {self.get_resultado_display()}"
