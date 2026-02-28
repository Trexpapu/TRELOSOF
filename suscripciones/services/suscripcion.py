"""
Servicio de suscripciones (Stripe Checkout).

Responsabilidades:
  - Crear la suscripción TRIAL al registrar la org
  - Cancelar la suscripción
  - Helpers de lectura (obtener_suscripcion, seleccionar_plan)

Nota: Los cobros, renovaciones y cambios de plan los maneja Stripe
      directamente (Checkout + Billing Portal). El webhook en views.py
      se encarga de sincronizar el estado en la BD.
"""

import stripe
import logging
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import Suscripcion

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Crear suscripción TRIAL al registrar
# ─────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def crear_suscripcion_trial(organizacion):
    """
    Crea el registro de suscripción en estado TRIAL.
    Se llama justo después de crear la organización en users/services/users.py.
    """
    if Suscripcion.objects.filter(organizacion=organizacion).exists():
        return Suscripcion.objects.get(organizacion=organizacion)

    ahora = timezone.now()
    suscripcion = Suscripcion.objects.create(
        organizacion=organizacion,
        estado='TRIAL',
        fecha_inicio=ahora,
        trial_fin=ahora + timedelta(days=settings.SUSCRIPCION_TRIAL_DIAS),
        precio_mensual=settings.SUSCRIPCION_PRECIO_MENSUAL,
    )
    logger.info(
        f"[SUSCRIPCION] Trial creado para org {organizacion.nombre} "
        f"({settings.SUSCRIPCION_TRIAL_DIAS} días), vence {suscripcion.trial_fin}"
    )
    return suscripcion


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cancelar suscripción
# ─────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def cancelar_suscripcion(suscripcion, user):
    """
    Marca la suscripción como CANCELADA.
    No se reembolsa; la organización sigue activa hasta el proximo_cobro.
    Solo el admin de la organización puede cancelar.
    """
    if not user.is_organizacion_admin:
        raise ValidationError("Solo el administrador puede cancelar la suscripción.")

    if suscripcion.organizacion != user.organizacion:
        raise ValidationError("No tienes permiso para cancelar esta suscripción.")

    if suscripcion.estado == 'CANCELADA':
        raise ValidationError("La suscripción ya está cancelada.")

    # Cancelar en Stripe si existe
    stripe.api_key = settings.STRIPE_SECRET_KEY
    if suscripcion.stripe_subscription_id:
        try:
            stripe.Subscription.cancel(suscripcion.stripe_subscription_id)
        except Exception as e:
            logger.warning(f"[SUSCRIPCION] No se pudo cancelar en Stripe: {e}")

    suscripcion.estado = 'CANCELADA'
    suscripcion.save(update_fields=['estado', 'updated_at'])
    logger.info(f"[SUSCRIPCION] Suscripción cancelada por {user.email} para {suscripcion.organizacion.nombre}")
    return suscripcion


# ─────────────────────────────────────────────────────────────────────────────
# 3. Obtener suscripción activa por organización
# ─────────────────────────────────────────────────────────────────────────────
def obtener_suscripcion(organizacion):
    """
    Retorna la suscripción de la organización, o None si no existe.
    """
    try:
        return Suscripcion.objects.get(organizacion=organizacion)
    except Suscripcion.DoesNotExist:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Seleccionar plan (primera vez – antes del primer checkout)
# ─────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def seleccionar_plan(suscripcion, plan):
    """
    Asigna el plan elegido y actualiza el precio_mensual.
    Se llama cuando el usuario elige plan por primera vez (antes del primer cobro).

    plan: 'BASICO' | 'PRO'
    """
    planes_validos = dict(Suscripcion.PLANES)
    if plan not in planes_validos:
        raise ValidationError(f"Plan inválido: {plan}. Opciones: {list(planes_validos.keys())}")

    precio = settings.PLAN_PRO_PRECIO if plan == 'PRO' else settings.PLAN_BASICO_PRECIO
    suscripcion.plan           = plan
    suscripcion.precio_mensual = precio
    suscripcion.save(update_fields=['plan', 'precio_mensual', 'updated_at'])
    logger.info(f"[PLAN] {suscripcion.organizacion.nombre} eligió plan {plan} (${precio}/mes)")
    return suscripcion
