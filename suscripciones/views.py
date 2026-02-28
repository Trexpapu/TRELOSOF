import json
import logging

import stripe

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

from .services.suscripcion import (
    cancelar_suscripcion,
    obtener_suscripcion,
    seleccionar_plan,
)
from .models import HistorialCobro, Suscripcion





# ─────────────────────────────────────────────────────────────────────────────
# Vista: cancelar suscripción
# ─────────────────────────────────────────────────────────────────────────────
@login_required
@require_POST
def cancelar_suscripcion_view(request):
    """
    Cancela la suscripción de la organización del usuario administrador.
    """
    if not request.user.is_organizacion_admin:
        messages.error(request, "Solo el administrador puede cancelar la suscripción.")
        return redirect('configuracion-index')

    suscripcion = obtener_suscripcion(request.user.organizacion)
    if not suscripcion:
        messages.error(request, "No se encontró una suscripción activa.")
        return redirect('configuracion-index')

    try:
        cancelar_suscripcion(suscripcion, request.user)
        messages.success(request, "Suscripción cancelada. Tu acceso permanece hasta la fecha de vencimiento.")
    except ValidationError as e:
        messages.error(request, e.message)

    return redirect('configuracion-index')






# ─────────────────────────────────────────────────────────────────────────────
# Vista: historial de cobros
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def historial_cobros(request):
    """
    Muestra el historial de todos los cobros de la organización.
    Solo visible para administradores.
    """
    if not request.user.is_organizacion_admin:
        messages.error(request, "Solo el administrador puede ver el historial de cobros.")
        return redirect('configuracion-index')

    suscripcion = obtener_suscripcion(request.user.organizacion)
    cobros = []
    if suscripcion:
        cobros = HistorialCobro.objects.filter(suscripcion=suscripcion).order_by('-fecha')

    return render(request, 'suscripciones/historial_cobros.html', {
        'suscripcion': suscripcion,
        'cobros': cobros,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Vista: Seleccionar plan inicial
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def seleccionar_plan_view(request):
    """
    Vista donde el usuario elige el plan Básico o Pro por primera vez.
    POST /suscripciones/plan/
    """
    if not request.user.is_organizacion_admin:
        messages.error(request, "Solo el administrador puede seleccionar o cambiar el plan.")
        return redirect('configuracion-index')

    suscripcion = obtener_suscripcion(request.user.organizacion)
    if not suscripcion:
        return redirect('index')

    if request.method == 'POST':
        plan = request.POST.get('plan')
        if not plan:
            messages.error(request, "Selecciona un plan.")
            return redirect('suscripcion-seleccionar-plan')
            
        try:
            seleccionar_plan(suscripcion, plan)
            messages.success(request, f"¡Has seleccionado el plan {dict(Suscripcion.PLANES)[plan]}!")
            return redirect('configuracion-index')
        except ValidationError as e:
            messages.error(request, str(e))
            
    return render(request, 'suscripciones/seleccionar_plan.html', {
        'suscripcion': suscripcion,
        'PLAN_BASICO_PRECIO': settings.PLAN_BASICO_PRECIO,
        'PLAN_PRO_PRECIO': settings.PLAN_PRO_PRECIO,
        'PLAN_BASICO_MAX_USUARIOS': settings.PLAN_BASICO_MAX_USUARIOS,
        'PLAN_PRO_MAX_USUARIOS': settings.PLAN_PRO_MAX_USUARIOS,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Vista: Cambiar de plan vía Stripe Billing Portal
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def cambiar_plan_view(request):
    """
    Redirige al Portal de Facturación de Stripe donde el usuario puede
    cambiar de plan, actualizar tarjeta o cancelar.
    Stripe se encarga de cobrar la diferencia y nos avisa vía webhook.
    """
    if not request.user.is_organizacion_admin:
        messages.error(request, "Solo el administrador puede cambiar el plan.")
        return redirect('configuracion-index')

    suscripcion = obtener_suscripcion(request.user.organizacion)
    if not suscripcion:
        return redirect('index')

    if not suscripcion.stripe_customer_id:
        messages.error(request, "Primero debes realizar un pago para poder gestionar tu plan.")
        return redirect('suscripcion-seleccionar-plan')

    stripe.api_key = settings.STRIPE_SECRET_KEY
    return_url = f"{settings.DOMAIN_URL}/configuracion/"

    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=suscripcion.stripe_customer_id,
            return_url=return_url,
        )
        return redirect(portal_session.url)
    except stripe.error.StripeError as e:
        logger.error(f'[PORTAL] Error al crear sesión del portal: {e}')
        messages.error(request, "No se pudo abrir el portal de facturación. Intenta de nuevo.")
        return redirect('configuracion-index')


# ─────────────────────────────────────────────────────────────────────────────
# Vista: Crear sesión de Stripe Checkout
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def crear_checkout_session(request, plan):
    """
    Crea una sesión de Stripe Checkout para el plan indicado ('BASICO' o 'PRO').
    Crea o reutiliza el Customer de Stripe (stripe_customer_id en Suscripcion).
    Redirige a session.url (página de pago hosteada por Stripe).
    """
    if not request.user.is_organizacion_admin:
        messages.error(request, "Solo el administrador puede iniciar el pago.")
        return redirect('configuracion-index')

    suscripcion = obtener_suscripcion(request.user.organizacion)
    if not suscripcion:
        messages.error(request, "No se encontró una suscripción para tu organización.")
        return redirect('configuracion-index')

    # Mapear el plan al Price ID de Stripe
    plan = plan.upper()
    price_ids = {
        'BASICO': settings.STRIPE_PRICE_ID_BASICO,
        'PRO':    settings.STRIPE_PRICE_ID_PRO,
    }
    price_id = price_ids.get(plan)
    if not price_id:
        messages.error(request, f"Plan '{plan}' no válido o Price ID no configurado en variables de entorno.")
        return redirect('suscripcion-seleccionar-plan')

    stripe.api_key = settings.STRIPE_SECRET_KEY
    organizacion   = request.user.organizacion

    # ── Crear o recuperar el Customer en Stripe ────────────────────────────────
    if not suscripcion.stripe_customer_id:
        admin_email = (
            organizacion.usuarios
            .filter(is_organizacion_admin=True)
            .values_list('email', flat=True)
            .first()
        )
        customer = stripe.Customer.create(
            email=admin_email,
            name=organizacion.nombre,
            metadata={'organizacion_id': str(organizacion.id)},
        )
        suscripcion.stripe_customer_id = customer.id
        suscripcion.save(update_fields=['stripe_customer_id', 'updated_at'])

    # ── Crear la sesión de Checkout ────────────────────────────────────────────
    try:
        session = stripe.checkout.Session.create(
            customer=suscripcion.stripe_customer_id,
            mode='subscription',
            line_items=[{'price': price_id, 'quantity': 1}],
            success_url=(
                f"{settings.DOMAIN_URL}"
                + "/suscripciones/checkout/exito/?session_id={CHECKOUT_SESSION_ID}"
            ),
            cancel_url=f"{settings.DOMAIN_URL}/suscripciones/plan/",
            metadata={
                'organizacion_id': str(organizacion.id),
                'plan':            plan,
            },
        )
        return redirect(session.url)
    except stripe.error.StripeError as e:
        messages.error(request, f"Error al crear la sesión de pago: {e.user_message}")
        return redirect('suscripcion-seleccionar-plan')


# ─────────────────────────────────────────────────────────────────────────────
# Vista: Éxito tras el pago en Stripe Checkout
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def checkout_exitoso(request):
    """
    Página de éxito a la que Stripe redirige tras el pago.
    Muestra un mensaje de confirmación; el webhook se encarga de actualizar
    el estado de la suscripción en base de datos.
    GET /suscripciones/checkout/exito/?session_id=...
    """
    messages.success(
        request,
        "✅ ¡Pago completado! Tu suscripción será activada en unos instantes."
    )
    return redirect('configuracion-index')


# ─────────────────────────────────────────────────────────────────────────────
# Vista: Stripe Webhook Handler
# Escucha eventos del ciclo de vida de la suscripción.
# IMPORTANTE: esta URL debe estar EXENTA de CSRF y autenticación.
# Registrar en el Dashboard de Stripe: POST /suscripciones/webhook/
# ─────────────────────────────────────────────────────────────────────────────
@csrf_exempt
def stripe_webhook(request):
    """
    Endpoint que Stripe llama cada vez que ocurre un evento relevante.
    Valida la firma del payload y despacha al handler correspondiente.
    """
    payload    = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    secret     = settings.STRIPE_WEBHOOK_SECRET

    # ── 1. Validar firma ─────────────────────────────────────────────────────
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, secret
        )
    except ValueError:
        # Payload inválido (no es JSON)
        logger.warning('[WEBHOOK] Payload inválido recibido de Stripe.')
        return HttpResponse('Payload inválido', status=400)
    except stripe.error.SignatureVerificationError:
        # Firma incorrecta – posible petición no autorizada
        logger.warning('[WEBHOOK] Firma de Stripe inválida. Petición rechazada.')
        return HttpResponse('Firma inválida', status=400)

    event_type = event['type']
    data       = event['data']['object']
    logger.info(f'[WEBHOOK] Evento recibido: {event_type} | id={event["id"]}')

    # =========================================================================
    # CASO A: checkout.session.completed
    # Ocurre cuando el usuario completa el pago en la página de Checkout.
    # Aquí activamos la suscripción por primera vez.
    # =========================================================================
    if event_type == 'checkout.session.completed':
        _handle_checkout_completed(data)

    # =========================================================================
    # CASO B: invoice.payment_succeeded
    # Ocurre cada mes cuando Stripe cobra la renovación automáticamente.
    # Aquí actualizamos proximo_cobro para mantener la suscripción activa.
    # =========================================================================
    elif event_type == 'invoice.payment_succeeded':
        _handle_invoice_paid(data)

    # =========================================================================
    # CASO C: customer.subscription.deleted
    # Ocurre cuando el usuario cancela o Stripe se rinde tras impagos.
    # Aquí marcamos la suscripción como VENCIDA.
    # =========================================================================
    elif event_type == 'customer.subscription.deleted':
        _handle_subscription_deleted(data)

    else:
        logger.debug(f'[WEBHOOK] Evento ignorado: {event_type}')

    return HttpResponse(status=200)


# ─────────────────────────────────────────────────────────────────────────────
# Handlers privados (uno por evento)
# ─────────────────────────────────────────────────────────────────────────────

def _handle_checkout_completed(session):
    """
    checkout.session.completed
    Activa la suscripción y guarda los IDs de Stripe.
    Busca la suscripción por organizacion_id (de la metadata), NO por email.
    """
    from .models import Suscripcion

    stripe.api_key = settings.STRIPE_SECRET_KEY

    stripe_customer_id      = session.get('customer')
    stripe_subscription_id  = session.get('subscription')
    metadata                = session.get('metadata', {})
    organizacion_id         = metadata.get('organizacion_id')
    plan_elegido            = (metadata.get('plan') or 'BASICO').upper()

    # Mapeo Price ID → plan
    price_map = {
        settings.STRIPE_PRICE_ID_BASICO: 'BASICO',
        settings.STRIPE_PRICE_ID_PRO:   'PRO',
    }

    # ── Buscar la Suscripcion local por organizacion_id (seguro) ──────────────
    if not organizacion_id:
        logger.error(
            '[WEBHOOK] checkout.session.completed: '
            'metadata no contiene organizacion_id. No se puede procesar.'
        )
        return

    try:
        suscripcion = Suscripcion.objects.get(organizacion_id=organizacion_id)
    except Suscripcion.DoesNotExist:
        logger.error(
            f'[WEBHOOK] checkout.session.completed: '
            f'No se encontró Suscripcion para organizacion_id={organizacion_id}'
        )
        return

    # ── Obtener detalles de la Suscripción de Stripe ──────────────────────────
    try:
        stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)
    except stripe.error.StripeError as e:
        logger.error(f'[WEBHOOK] Error al recuperar suscripción de Stripe: {e}')
        return

    # Detectar plan por price_id
    current_price_id = (
        stripe_sub['items']['data'][0]['price']['id']
        if stripe_sub.get('items') and stripe_sub['items']['data']
        else None
    )
    plan = price_map.get(current_price_id, plan_elegido)

    # Convertir current_period_end (Unix timestamp) a datetime aware
    proximo_cobro = timezone.datetime.fromtimestamp(
        stripe_sub['current_period_end'],
        tz=timezone.utc
    )

    # ── Actualizar el modelo local ────────────────────────────────────────────
    suscripcion.stripe_customer_id     = stripe_customer_id
    suscripcion.stripe_subscription_id = stripe_subscription_id
    suscripcion.estado                 = 'ACTIVA'
    suscripcion.plan                   = plan
    suscripcion.proximo_cobro          = proximo_cobro
    suscripcion.save(update_fields=[
        'stripe_customer_id',
        'stripe_subscription_id',
        'estado',
        'plan',
        'proximo_cobro',
        'updated_at',
    ])

    logger.info(
        f'[WEBHOOK] Suscripción ACTIVADA | org={suscripcion.organizacion.nombre} '
        f'| plan={plan} | próximo cobro={proximo_cobro.strftime("%d/%m/%Y")}'
    )


def _handle_invoice_paid(invoice):
    """
    invoice.payment_succeeded
    Renueva la fecha de corte mensualmente.
    """
    from .models import Suscripcion

    stripe_subscription_id = invoice.get('subscription')
    if not stripe_subscription_id:
        logger.warning('[WEBHOOK] invoice.payment_succeeded sin subscription_id. Ignorado.')
        return

    suscripcion = Suscripcion.objects.filter(
        stripe_subscription_id=stripe_subscription_id
    ).first()

    if not suscripcion:
        logger.warning(
            f'[WEBHOOK] invoice.payment_succeeded: '
            f'No se encontró Suscripcion para subscription_id={stripe_subscription_id}'
        )
        return

    # Obtener la nueva fecha de fin de período desde la primera línea de la factura
    try:
        period_end = invoice['lines']['data'][0]['period']['end']
        proximo_cobro = timezone.datetime.fromtimestamp(
            period_end,
            tz=timezone.utc
        )
    except (KeyError, IndexError, TypeError) as e:
        logger.error(f'[WEBHOOK] No se pudo leer period.end del invoice: {e}')
        return

    suscripcion.estado        = 'ACTIVA'
    suscripcion.proximo_cobro = proximo_cobro
    suscripcion.save(update_fields=['estado', 'proximo_cobro', 'updated_at'])

    logger.info(
        f'[WEBHOOK] Renovación exitosa | org={suscripcion.organizacion.nombre} '
        f'| próximo cobro={proximo_cobro.strftime("%d/%m/%Y")}'
    )


def _handle_subscription_deleted(stripe_sub):
    """
    customer.subscription.deleted
    Marca la suscripción como VENCIDA cuando Stripe la cancela.
    """
    from .models import Suscripcion

    stripe_subscription_id = stripe_sub.get('id')

    suscripcion = Suscripcion.objects.filter(
        stripe_subscription_id=stripe_subscription_id
    ).first()

    if not suscripcion:
        logger.warning(
            f'[WEBHOOK] customer.subscription.deleted: '
            f'No se encontró Suscripcion para subscription_id={stripe_subscription_id}'
        )
        return

    suscripcion.estado = 'VENCIDA'
    suscripcion.save(update_fields=['estado', 'updated_at'])

    logger.warning(
        f'[WEBHOOK] Suscripción VENCIDA (cancelada por Stripe) '
        f'| org={suscripcion.organizacion.nombre} '
        f'| subscription_id={stripe_subscription_id}'
    )
