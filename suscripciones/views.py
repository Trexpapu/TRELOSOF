import datetime
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
        fecha_fin = suscripcion.proximo_cobro.strftime('%d/%m/%Y') if suscripcion.proximo_cobro else 'el fin del período actual'
        messages.success(
            request,
            f"Tu suscripción se cancelará automáticamente el {fecha_fin}. "
            f"Hasta entonces, conservas acceso completo."
        )
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
# Vista: Cambiar de plan (upgrade inmediato / downgrade al final del período)
# ─────────────────────────────────────────────────────────────────────────────
@login_required
@require_POST
def cambiar_plan_view(request):
    """
    Upgrade: Stripe.Subscription.modify inmediato con proration.
    Downgrade: Subscription Schedule → cambio al final del período.
    """
    if not request.user.is_organizacion_admin:
        messages.error(request, "Solo el administrador puede cambiar el plan.")
        return redirect('configuracion-index')

    suscripcion = obtener_suscripcion(request.user.organizacion)
    if not suscripcion or not suscripcion.stripe_subscription_id:
        messages.error(request, "Primero debes tener una suscripción activa.")
        return redirect('suscripcion-seleccionar-plan')

    nuevo_plan = (request.POST.get('plan') or '').upper()
    if nuevo_plan not in ('BASICO', 'PRO'):
        messages.error(request, "Plan no válido.")
        return redirect('configuracion-index')

    if nuevo_plan == suscripcion.plan:
        messages.info(request, "Ya estás en ese plan.")
        return redirect('configuracion-index')

    # Bloquear si ya hay un cambio pendiente
    if suscripcion.has_pending_change:
        messages.warning(
            request,
            f"Ya tienes un cambio programado al Plan {suscripcion.pending_plan_display} "
            f"para el {suscripcion.pending_plan_date.strftime('%d/%m/%Y') if suscripcion.pending_plan_date else 'próximo período'}. "
            f"No puedes cambiar de plan hasta que se aplique."
        )
        return redirect('configuracion-index')

    stripe.api_key = settings.STRIPE_SECRET_KEY
    PLAN_ORDER = {'BASICO': 1, 'PRO': 2}
    is_upgrade = PLAN_ORDER.get(nuevo_plan, 0) > PLAN_ORDER.get(suscripcion.plan, 0)

    price_map = {
        'BASICO': settings.STRIPE_PRICE_ID_BASICO,
        'PRO':    settings.STRIPE_PRICE_ID_PRO,
    }
    new_price_id = price_map[nuevo_plan]

    try:
        # Recuperar la suscripción de Stripe para obtener el item_id
        stripe_sub = stripe.Subscription.retrieve(
            suscripcion.stripe_subscription_id,
            expand=['items.data'],
        )
        item_id = stripe_sub['items']['data'][0]['id']

        if is_upgrade:
            # ── UPGRADE: Cambio inmediato con prorrateo ──────────────────────
            # Si hay un schedule pendiente (downgrade anterior), cancelarlo primero
            existing_schedule_id = stripe_sub.get('schedule') or suscripcion.stripe_schedule_id
            if existing_schedule_id:
                try:
                    stripe.SubscriptionSchedule.release(existing_schedule_id)
                    logger.info(f'[PLAN] Schedule {existing_schedule_id} liberado para permitir upgrade')
                except stripe.error.StripeError:
                    pass  # Si ya no existe, no importa

            stripe.Subscription.modify(
                suscripcion.stripe_subscription_id,
                items=[{'id': item_id, 'price': new_price_id}],
                proration_behavior='create_prorations',
            )
            precio = settings.PLAN_PRO_PRECIO if nuevo_plan == 'PRO' else settings.PLAN_BASICO_PRECIO
            suscripcion.plan = nuevo_plan
            suscripcion.precio_mensual = precio
            suscripcion.pending_plan = None
            suscripcion.pending_plan_date = None
            suscripcion.stripe_schedule_id = None
            suscripcion.save(update_fields=[
                'plan', 'precio_mensual',
                'pending_plan', 'pending_plan_date', 'stripe_schedule_id',
                'updated_at',
            ])

            logger.info(
                f'[PLAN] UPGRADE inmediato | org={suscripcion.organizacion.nombre} '
                f'| {suscripcion.plan} → {nuevo_plan}'
            )
            messages.success(
                request,
                f"¡Plan actualizado a {nuevo_plan}! El cambio se aplicó de inmediato."
            )
        else:
            # ── DOWNGRADE: Programar cambio al final del período ─────────────
            existing_schedule_id = stripe_sub.get('schedule') or suscripcion.stripe_schedule_id

            if existing_schedule_id:
                # Ya tiene un schedule → modificarlo con las nuevas fases
                schedule = stripe.SubscriptionSchedule.retrieve(existing_schedule_id)
            else:
                # No tiene schedule → crear uno desde la suscripción
                schedule = stripe.SubscriptionSchedule.create(
                    from_subscription=suscripcion.stripe_subscription_id,
                )

            current_price_id = price_map.get(suscripcion.plan, settings.STRIPE_PRICE_ID_BASICO)
            current_phase = schedule.phases[0]

            stripe.SubscriptionSchedule.modify(
                schedule.id,
                end_behavior='release',
                phases=[
                    {
                        'items': [{'price': current_price_id}],
                        'start_date': current_phase.start_date,
                        'end_date': current_phase.end_date,
                    },
                    {
                        'items': [{'price': new_price_id}],
                        'proration_behavior': 'none',
                    },
                ],
            )

            suscripcion.pending_plan = nuevo_plan
            suscripcion.pending_plan_date = suscripcion.proximo_cobro
            suscripcion.stripe_schedule_id = schedule.id
            suscripcion.save(update_fields=[
                'pending_plan', 'pending_plan_date', 'stripe_schedule_id',
                'updated_at',
            ])

            fecha_str = suscripcion.proximo_cobro.strftime('%d/%m/%Y') if suscripcion.proximo_cobro else 'el próximo período'
            logger.info(
                f'[PLAN] DOWNGRADE programado | org={suscripcion.organizacion.nombre} '
                f'| {suscripcion.plan} → {nuevo_plan} | Aplica: {fecha_str}'
            )
            messages.success(
                request,
                f"Tu cambio al Plan {nuevo_plan} se aplicará el {fecha_str}. "
                f"Hasta entonces, conservas todas las funciones de tu plan actual."
            )

    except stripe.error.StripeError as e:
        logger.error(f'[PLAN] Error al cambiar plan: {e}')
        messages.error(request, f"Error al procesar el cambio de plan: {e.user_message or 'Intenta de nuevo.'}")

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

    # =========================================================================
    # CASO D: customer.subscription.updated
    # Ocurre cuando Stripe aplica un cambio de plan (upgrade/downgrade/schedule).
    # Aquí sincronizamos el plan real con nuestra BD.
    # =========================================================================
    elif event_type == 'customer.subscription.updated':
        _handle_subscription_updated(data)

    # =========================================================================
    # CASO E: subscription_schedule.released
    # Ocurre cuando un Schedule completa su última fase y se disuelve.
    # Limpiamos los campos pending_plan de nuestra BD.
    # =========================================================================
    elif event_type == 'subscription_schedule.released':
        _handle_schedule_released(data)

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
        stripe_sub = stripe.Subscription.retrieve(
            stripe_subscription_id,
            expand=['items.data'],
        )
    except stripe.error.StripeError as e:
        logger.error(f'[WEBHOOK] Error al recuperar suscripción de Stripe: {e}')
        return

    # Detectar plan por price_id
    items_data = []
    try:
        items_data = stripe_sub['items']['data']
    except (KeyError, TypeError):
        try:
            items_data = stripe_sub['items']['data']
        except (KeyError, TypeError):
            pass

    current_price_id = None
    if items_data:
        try:
            current_price_id = items_data[0].price.id
        except AttributeError:
            try:
                current_price_id = items_data[0]['price']['id']
            except (KeyError, TypeError):
                pass

    plan = price_map.get(current_price_id, plan_elegido)

    # ── Obtener current_period_end ────────────────────────────────────────────
    # En Stripe SDK v14+ (API 2025+), current_period_end está en items.data[0],
    # NO en el nivel raíz del Subscription.
    period_end_ts = None

    # Intento 1: desde items.data[0] (SDK v14+ / API 2025+)
    if items_data:
        try:
            period_end_ts = items_data[0].current_period_end
        except AttributeError:
            try:
                period_end_ts = items_data[0]['current_period_end']
            except (KeyError, TypeError):
                pass

    # Intento 2: atributo directo (APIs más antiguas)
    if not period_end_ts:
        period_end_ts = getattr(stripe_sub, 'current_period_end', None)
        if not period_end_ts:
            try:
                period_end_ts = stripe_sub['current_period_end']
            except (KeyError, TypeError):
                pass

    # Fallback: +30 días desde ahora
    if period_end_ts:
        proximo_cobro = datetime.datetime.fromtimestamp(
            period_end_ts, tz=datetime.timezone.utc
        )
    else:
        from datetime import timedelta
        proximo_cobro = timezone.now() + timedelta(days=30)
        logger.warning(
            f'[WEBHOOK] No se encontró current_period_end en Subscription '
            f'{stripe_subscription_id}. Usando fallback +30 días.'
        )

    # ── Actualizar el modelo local ────────────────────────────────────────────
    precio = settings.PLAN_PRO_PRECIO if plan == 'PRO' else settings.PLAN_BASICO_PRECIO
    suscripcion.stripe_customer_id     = stripe_customer_id
    suscripcion.stripe_subscription_id = stripe_subscription_id
    suscripcion.estado                 = 'ACTIVA'
    suscripcion.plan                   = plan
    suscripcion.precio_mensual         = precio
    suscripcion.proximo_cobro          = proximo_cobro
    suscripcion.save(update_fields=[
        'stripe_customer_id',
        'stripe_subscription_id',
        'estado',
        'plan',
        'precio_mensual',
        'proximo_cobro',
        'updated_at',
    ])

    # NOTA: No creamos HistorialCobro aquí para evitar duplicados.
    # El registro se crea en _handle_invoice_paid (invoice.payment_succeeded),
    # que siempre se dispara junto con checkout.session.completed.

    logger.info(
        f'[WEBHOOK] Suscripción ACTIVADA | org={suscripcion.organizacion.nombre} '
        f'| plan={plan} | próximo cobro={proximo_cobro.strftime("%d/%m/%Y")}'
    )


def _handle_invoice_paid(invoice):
    """
    invoice.payment_succeeded
    Renueva la fecha de corte mensualmente.
    También intenta buscar por customer_id si no encuentra por subscription_id
    (ocurre en la primera factura del checkout).
    """
    from .models import Suscripcion

    stripe_subscription_id = invoice.get('subscription')

    suscripcion = None

    # Intento 1: buscar por subscription_id
    if stripe_subscription_id:
        suscripcion = Suscripcion.objects.filter(
            stripe_subscription_id=stripe_subscription_id
        ).first()

    # Intento 2: buscar por customer_id (fallback para primera factura)
    if not suscripcion:
        stripe_customer_id = invoice.get('customer')
        if stripe_customer_id:
            suscripcion = Suscripcion.objects.filter(
                stripe_customer_id=stripe_customer_id
            ).first()

    if not suscripcion:
        logger.debug(
            f'[WEBHOOK] invoice.payment_succeeded: '
            f'No se encontró Suscripcion para subscription_id={stripe_subscription_id}. '
            f'Podría ser una factura sin suscripción asociada. Ignorado.'
        )
        return

    # Obtener la nueva fecha de fin de período desde la primera línea de la factura
    try:
        lines_data = invoice.get('lines', {}).get('data', [])
        if not lines_data:
            # Intentar con atributo directo (Stripe SDK objects)
            lines_data = getattr(getattr(invoice, 'lines', None), 'data', [])

        period_end = lines_data[0]['period']['end']
        proximo_cobro = datetime.datetime.fromtimestamp(
            period_end,
            tz=datetime.timezone.utc
        )
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        logger.error(f'[WEBHOOK] No se pudo leer period.end del invoice: {e}')
        return

    suscripcion.estado        = 'ACTIVA'
    suscripcion.proximo_cobro = proximo_cobro
    suscripcion.save(update_fields=['estado', 'proximo_cobro', 'updated_at'])

    # ── Registrar en historial de cobros ──────────────────────────────────────
    monto_cobrado = invoice.get('amount_paid', 0) / 100  # Stripe usa centavos
    if monto_cobrado > 0:
        from .models import HistorialCobro
        billing_reason = invoice.get('billing_reason', '')
        if billing_reason == 'subscription_create':
            descripcion = f'Pago inicial – Plan {suscripcion.plan}'
        elif billing_reason == 'subscription_cycle':
            descripcion = 'Renovación mensual'
        elif billing_reason == 'subscription_update':
            descripcion = 'Ajuste por cambio de plan'
        else:
            descripcion = f'Pago – {billing_reason or "Stripe"}'

        HistorialCobro.objects.create(
            suscripcion=suscripcion,
            monto=monto_cobrado,
            resultado='EXITOSO',
            stripe_charge_id=invoice.get('payment_intent', ''),
            descripcion=descripcion,
        )

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


def _handle_subscription_updated(stripe_sub):
    """
    customer.subscription.updated
    Cuando Stripe aplica un cambio de plan (por schedule u otro motivo),
    sincronizamos el plan y precio en nuestra BD y limpiamos pending_plan.
    """
    from .models import Suscripcion

    stripe_subscription_id = stripe_sub.get('id')
    suscripcion = Suscripcion.objects.filter(
        stripe_subscription_id=stripe_subscription_id
    ).first()

    if not suscripcion:
        logger.debug(
            f'[WEBHOOK] customer.subscription.updated: '
            f'No se encontró Suscripcion para subscription_id={stripe_subscription_id}'
        )
        return

    # Mapeo Price ID → plan
    price_map = {
        settings.STRIPE_PRICE_ID_BASICO: 'BASICO',
        settings.STRIPE_PRICE_ID_PRO:   'PRO',
    }

    # Detectar el plan actual en Stripe
    items_data = []
    try:
        items_data = stripe_sub.get('items', {}).get('data', [])
    except (AttributeError, TypeError):
        pass

    if not items_data:
        return

    try:
        current_price_id = items_data[0]['price']['id']
    except (KeyError, IndexError, TypeError):
        return

    nuevo_plan = price_map.get(current_price_id)
    if not nuevo_plan or nuevo_plan == suscripcion.plan:
        return  # Sin cambio real de plan

    # Aplicar el cambio
    precio = settings.PLAN_PRO_PRECIO if nuevo_plan == 'PRO' else settings.PLAN_BASICO_PRECIO
    suscripcion.plan = nuevo_plan
    suscripcion.precio_mensual = precio
    suscripcion.pending_plan = None
    suscripcion.pending_plan_date = None
    suscripcion.stripe_schedule_id = None
    suscripcion.save(update_fields=[
        'plan', 'precio_mensual',
        'pending_plan', 'pending_plan_date', 'stripe_schedule_id',
        'updated_at',
    ])

    logger.info(
        f'[WEBHOOK] Plan actualizado vía subscription.updated '
        f'| org={suscripcion.organizacion.nombre} | plan={nuevo_plan}'
    )


def _handle_schedule_released(schedule):
    """
    subscription_schedule.released
    El schedule completó todas sus fases y se disolvió.
    Limpiamos los campos pending_plan de la suscripción.
    """
    from .models import Suscripcion

    schedule_id = schedule.get('id')
    suscripcion = Suscripcion.objects.filter(
        stripe_schedule_id=schedule_id
    ).first()

    if not suscripcion:
        logger.debug(
            f'[WEBHOOK] subscription_schedule.released: '
            f'No se encontró Suscripcion para schedule_id={schedule_id}'
        )
        return

    suscripcion.pending_plan = None
    suscripcion.pending_plan_date = None
    suscripcion.stripe_schedule_id = None
    suscripcion.save(update_fields=[
        'pending_plan', 'pending_plan_date', 'stripe_schedule_id',
        'updated_at',
    ])

    logger.info(
        f'[WEBHOOK] Schedule released | org={suscripcion.organizacion.nombre} '
        f'| schedule_id={schedule_id}'
    )
