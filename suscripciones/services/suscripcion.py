"""
Servicio de suscripciones.

Responsabilidades:
  - Crear la suscripción TRIAL al registrar la org
  - Guardar el método de pago (token de Stripe)
  - Crear el customer en Stripe
  - Ejecutar el primer cobro (y los siguientes mensuales)
  - Cancelar la suscripción
  - Cambiar el método de pago

Reglas de negocio:
  - La prueba dura 14 días contados desde el registro
  - Si al día 14 tiene método de pago → se cobra automáticamente
  - Si no tiene método de pago → pasa a VENCIDA
  - Después del primer cobro exitoso → estado ACTIVA con proximo_cobro = +30 días
"""

import stripe
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import Suscripcion, HistorialCobro

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Helper interno: configurar la clave de Stripe
# ─────────────────────────────────────────────────────────────────────────────
def _stripe():
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


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
# 2. Guardar / actualizar método de pago
# ─────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def guardar_metodo_pago(suscripcion, payment_method_id):
    """
    Asocia un PaymentMethod de Stripe al customer de la organización.
    Si el customer no existe, lo crea primero.

    payment_method_id: str (pm_xxxxxxxx) generado en el frontend con Stripe.js
    """
    s = _stripe()
    organizacion = suscripcion.organizacion

    # ── Crear o recuperar el customer en Stripe ────────────────────────────
    if not suscripcion.stripe_customer_id:
        customer = s.Customer.create(
            email=organizacion.usuarios.filter(is_organizacion_admin=True).values_list('email', flat=True).first(),
            name=organizacion.nombre,
            metadata={'organizacion_id': str(organizacion.id)},
        )
        suscripcion.stripe_customer_id = customer.id

    # ── Adjuntar el PaymentMethod al customer ──────────────────────────────
    s.PaymentMethod.attach(
        payment_method_id,
        customer=suscripcion.stripe_customer_id,
    )

    # ── Definirlo como default ─────────────────────────────────────────────
    s.Customer.modify(
        suscripcion.stripe_customer_id,
        invoice_settings={'default_payment_method': payment_method_id},
    )

    # ── Obtener detalles de la tarjeta para mostrar ────────────────────────
    pm = s.PaymentMethod.retrieve(payment_method_id)
    card = pm.get('card', {})

    suscripcion.stripe_payment_method_id = payment_method_id
    suscripcion.card_brand     = card.get('brand')
    suscripcion.card_last4     = card.get('last4')
    suscripcion.card_exp_month = card.get('exp_month')
    suscripcion.card_exp_year  = card.get('exp_year')
    suscripcion.save()

    logger.info(f"[SUSCRIPCION] Método de pago guardado para {organizacion.nombre}: **** {suscripcion.card_last4}")
    return suscripcion


# ─────────────────────────────────────────────────────────────────────────────
# 3. Ejecutar cobro (trial → activa, o cobro mensual)
# ─────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def ejecutar_cobro(suscripcion):
    """
    Cobra el monto mensual al método de pago guardado.
    Solo permite cobrar si la suscripción está vencida o a punto de vencer.
    (proximo_cobro <= ahora)
    """
    if not suscripcion.stripe_payment_method_id:
        raise ValidationError("La organización no tiene método de pago registrado.")

    if not suscripcion.stripe_customer_id:
        raise ValidationError("La organización no tiene customer de Stripe.")

    ahora = timezone.now()
    if suscripcion.proximo_cobro and suscripcion.proximo_cobro > ahora:
        raise ValidationError("Tu suscripción no está vencida. Solo puedes pagar cuando llegue tu fecha de corte.")

    s = _stripe()
    monto_centavos = int(suscripcion.precio_mensual * 100)  # Stripe usa centavos

    try:
        payment_intent = s.PaymentIntent.create(
            amount=monto_centavos,
            currency='mxn',
            customer=suscripcion.stripe_customer_id,
            payment_method=suscripcion.stripe_payment_method_id,
            confirm=True,
            off_session=True,
            description=f'Suscripción mensual TRE BANKS – {suscripcion.organizacion.nombre}',
        )

        # ── Calcular el nuevo proximo_cobro ──
        nuevo_proximo = ahora + timedelta(days=settings.SUSCRIPCION_CICLO_DIAS)

        suscripcion.estado = 'ACTIVA'
        suscripcion.proximo_cobro = nuevo_proximo
        suscripcion.save(update_fields=['estado', 'proximo_cobro', 'updated_at'])

        HistorialCobro.objects.create(
            suscripcion=suscripcion,
            monto=suscripcion.precio_mensual,
            resultado='EXITOSO',
            stripe_charge_id=payment_intent.id,
            descripcion='Cobro de suscripción',
        )
        logger.info(
            f"[SUSCRIPCION] Cobro exitoso para {suscripcion.organizacion.nombre}: "
            f"${suscripcion.precio_mensual} – próximo cobro: {nuevo_proximo.strftime('%d/%m/%Y')}"
        )
        return suscripcion

    except s.error.CardError as e:
        # ── Cobro fallido – NO marcar como VENCIDA si aún hay crédito ─────────
        if not suscripcion.dias_cubiertos:
            suscripcion.estado = 'VENCIDA'
            suscripcion.save(update_fields=['estado', 'updated_at'])

        HistorialCobro.objects.create(
            suscripcion=suscripcion,
            monto=suscripcion.precio_mensual,
            resultado='FALLIDO',
            descripcion=str(e),
        )
        logger.warning(f"[SUSCRIPCION] Cobro fallido para {suscripcion.organizacion.nombre}: {e}")
        raise ValidationError(f"El cobro fue rechazado: {e.user_message}")



# ─────────────────────────────────────────────────────────────────────────────
# 4. Cancelar suscripción
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
    s = _stripe()
    if suscripcion.stripe_subscription_id:
        try:
            s.Subscription.cancel(suscripcion.stripe_subscription_id)
        except Exception as e:
            logger.warning(f"[SUSCRIPCION] No se pudo cancelar en Stripe: {e}")

    suscripcion.estado = 'CANCELADA'
    suscripcion.save(update_fields=['estado', 'updated_at'])
    logger.info(f"[SUSCRIPCION] Suscripción cancelada por {user.email} para {suscripcion.organizacion.nombre}")
    return suscripcion


# ─────────────────────────────────────────────────────────────────────────────
# 5. Obtener suscripción activa por organización
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
# 6. Seleccionar plan (primera vez – al primer cobro real)
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


# ─────────────────────────────────────────────────────────────────────────────
# 7. Cambiar de plan (upgrade/downgrade)
# ─────────────────────────────────────────────────────────────────────────────
@transaction.atomic
def cambiar_plan(suscripcion, nuevo_plan):
    """
    Aplica el cambio de plan de forma inmediata.
    El próximo cobro reflejará el nuevo precio.
    Devuelve un dict con información descriptiva.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    if nuevo_plan not in dict(Suscripcion.PLANES):
        raise ValidationError(f"Plan inválido: {nuevo_plan}")

    if nuevo_plan == suscripcion.plan:
        raise ValidationError("Ya estás en ese plan.")

    # ── Validación de downgrade: ¿tienen más usuarios de los que permite el nuevo plan? ──
    limit_nuevo = settings.PLAN_PRO_MAX_USUARIOS if nuevo_plan == 'PRO' else settings.PLAN_BASICO_MAX_USUARIOS
    total_usuarios = User.objects.filter(organizacion=suscripcion.organizacion).count()
    
    if total_usuarios > limit_nuevo:
        raise ValidationError(
            f"No puedes cambiar al plan {dict(Suscripcion.PLANES)[nuevo_plan]}. "
            f"Este plan admite hasta {limit_nuevo} usuarios, pero tu organización "
            f"actualmente tiene {total_usuarios} usuarios activos. "
            f"Por favor, elimina empleados desde la sección 'Gestión de Usuarios' e intenta de nuevo."
        )

    precio_nuevo = settings.PLAN_PRO_PRECIO if nuevo_plan == 'PRO' else settings.PLAN_BASICO_PRECIO

    suscripcion.plan           = nuevo_plan
    suscripcion.precio_mensual = precio_nuevo
    suscripcion.save(update_fields=['plan', 'precio_mensual', 'updated_at'])
    logger.info(f"[PLAN] Cambio a {nuevo_plan} para {suscripcion.organizacion.nombre}")
    
    return {
        'inmediato': True,
        'info': f"Tu plan cambió a {dict(Suscripcion.PLANES)[nuevo_plan]} exitosamente. "
                f"Tu límite de usuarios ha sido actualizado."
    }
