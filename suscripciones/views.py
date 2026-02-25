from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.conf import settings
from django.core.exceptions import ValidationError
import stripe

from .services.suscripcion import (
    guardar_metodo_pago,
    cancelar_suscripcion,
    obtener_suscripcion,
    ejecutar_cobro,
    seleccionar_plan,
    cambiar_plan,
)
from .models import HistorialCobro, Suscripcion


# ─────────────────────────────────────────────────────────────────────────────
# Vista: agregar / actualizar método de pago
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def agregar_metodo_pago(request):
    """
    Muestra el formulario de tarjeta (Stripe.js).
    POST: guarda el PaymentMethod generado en el frontend.
    """
    if not request.user.is_organizacion_admin:
        messages.error(request, "Solo el administrador puede gestionar el método de pago.")
        return redirect('configuracion-index')

    suscripcion = obtener_suscripcion(request.user.organizacion)
    if not suscripcion:
        messages.error(request, "No se encontró una suscripción para tu organización.")
        return redirect('configuracion-index')

    if request.method == 'POST':
        payment_method_id = request.POST.get('payment_method_id')
        if not payment_method_id:
            messages.error(request, "No se recibió el método de pago. Inténtalo nuevamente.")
            return render(request, 'suscripciones/agregar_metodo_pago.html', {
                'suscripcion': suscripcion,
                'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
            })
        try:
            guardar_metodo_pago(suscripcion, payment_method_id)
            messages.success(request, "Método de pago guardado correctamente.")
            return redirect('configuracion-index')
        except (ValidationError, stripe.error.StripeError) as e:
            messages.error(request, f"Error al guardar el método de pago: {e}")

    return render(request, 'suscripciones/agregar_metodo_pago.html', {
        'suscripcion': suscripcion,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
    })


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
# Vista: método de pago en el registro (paso 2 del registro)
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def metodo_pago_registro(request):
    """
    Página de método de pago que aparece justo después de registrarse.
    El usuario puede omitirla (tendrá X días sin pagar) o agregarla ahora.
    """
    suscripcion = obtener_suscripcion(request.user.organizacion)
    if not suscripcion:
        return redirect('index')

    if request.method == 'POST':
        payment_method_id = request.POST.get('payment_method_id')
        if payment_method_id:
            try:
                guardar_metodo_pago(suscripcion, payment_method_id)
                messages.success(request, "¡Método de pago guardado! Tu suscripción está lista.")
            except (ValidationError, stripe.error.StripeError) as e:
                messages.error(request, f"Error al guardar el método de pago: {e}")
                return render(request, 'suscripciones/metodo_pago_registro.html', {
                    'suscripcion': suscripcion,
                    'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
                })
        return redirect('index')

    return render(request, 'suscripciones/metodo_pago_registro.html', {
        'suscripcion': suscripcion,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Vista: cobro manual (SOLO PRUEBAS – úsala para cobrar sin esperar el cron)
# ─────────────────────────────────────────────────────────────────────────────
@login_required
@require_POST
def ejecutar_cobro_manual(request):
    """
    Dispara el cobro inmediatamente sobre la suscripción activa.
    Solo disponible para administradores.
    Útil durante pruebas: evita tener que esperar al cron diario.
    """
    if not request.user.is_organizacion_admin:
        messages.error(request, "Solo el administrador puede ejecutar cobros.")
        return redirect('configuracion-index')

    suscripcion = obtener_suscripcion(request.user.organizacion)
    if not suscripcion:
        messages.error(request, "No se encontró una suscripción.")
        return redirect('configuracion-index')

    if not suscripcion.tiene_metodo_pago:
        messages.error(request, "Agrega primero un método de pago antes de cobrar.")
        return redirect('suscripcion-metodo-pago')

    try:
        ejecutar_cobro(suscripcion)
        # Recargar para obtener el proximo_cobro actualizado
        suscripcion.refresh_from_db()
        fecha_prox = suscripcion.proximo_cobro.strftime('%d/%m/%Y') if suscripcion.proximo_cobro else '—'
        
        msg = f"✅ Cobro de ${suscripcion.precio_mensual} MXN ejecutado. Próximo cobro: {fecha_prox}."
        messages.success(request, msg)
        # Redirige al inicio para que el usuario vea que recuperó acceso
        return redirect('index')
    except ValidationError as e:
        messages.error(request, f"❌ El cobro falló: {e.message}")

    return redirect('suscripcion-historial')


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
# Vista: Cambiar de plan (Upgrade / Downgrade)
# ─────────────────────────────────────────────────────────────────────────────
@login_required
@require_POST
def cambiar_plan_view(request):
    """
    Vista procesar cambio de plan.
    POST /suscripciones/cambiar-plan/
    """
    if not request.user.is_organizacion_admin:
        messages.error(request, "Solo el administrador puede cambiar el plan.")
        return redirect('configuracion-index')

    suscripcion = obtener_suscripcion(request.user.organizacion)
    if not suscripcion:
        return redirect('index')

    nuevo_plan = request.POST.get('plan')
    try:
        resultado = cambiar_plan(suscripcion, nuevo_plan)
        messages.success(request, resultado['info'])
    except ValidationError as e:
        messages.error(request, str(e))

    return redirect('configuracion-index')
