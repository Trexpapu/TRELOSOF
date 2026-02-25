"""
App configuracion – hub de configuración de cuenta.

Agrupa:
  - Cambio de contraseña
  - Gestión de suscripción (método de pago, cancelar)
  - Vista del panel principal de configuración
  - 2FA (TOTP – Authy / Google Authenticator)
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ValidationError
import io, base64, pyotp, qrcode
from users.models import BackupCode, generate_backup_codes

from users.forms import ChangePasswordForm
from suscripciones.services.suscripcion import obtener_suscripcion


# ─────────────────────────────────────────────────────────────────────────────
# Panel principal de Configuración
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def configuracion_index(request):
    suscripcion = obtener_suscripcion(request.user.organizacion) if request.user.organizacion else None
    return render(request, 'configuracion/index.html', {
        'suscripcion': suscripcion,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Cambio de contraseña
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def cambiar_contrasena(request):
    """Permite al usuario cambiar su contraseña."""
    if request.method == 'POST':
        form = ChangePasswordForm(request.POST)
        if form.is_valid():
            user = request.user
            current_password = form.cleaned_data['current_password']
            new_password = form.cleaned_data['new_password']

            if not user.check_password(current_password):
                form.add_error('current_password', 'La contraseña actual es incorrecta.')
            else:
                user.set_password(new_password)
                user.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Contraseña actualizada correctamente.')
                return redirect('configuracion-index')
    else:
        form = ChangePasswordForm()

    return render(request, 'configuracion/change_password.html', {'form': form})


# ─────────────────────────────────────────────────────────────────────────────
# 2FA – Setup: generar QR y secreto temporal
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def setup_2fa(request):
    """
    Muestra el QR para vincular Authy.
    El secreto se genera y guarda en sesión hasta que el usuario lo confirme
    con un token válido (vista confirmar_2fa).
    """
    user = request.user

    if user.totp_enabled:
        messages.info(request, '2FA ya está activado en tu cuenta.')
        return redirect('configuracion-index')

    # Generar nuevo secreto y guardarlo en sesión (no en BD hasta confirmar)
    secret = pyotp.random_base32()
    request.session['totp_secret_pending'] = secret

    # Construir URI TOTP compatible con Authy / Google Authenticator
    app_name = 'TRE BANKS'
    totp_uri  = pyotp.totp.TOTP(secret).provisioning_uri(
        name=user.email,
        issuer_name=app_name,
    )

    # Generar QR como imagen base64 para incrustar en HTML
    qr_img  = qrcode.make(totp_uri)
    buffer  = io.BytesIO()
    qr_img.save(buffer, format='PNG')
    qr_b64  = base64.b64encode(buffer.getvalue()).decode()

    return render(request, 'configuracion/setup_2fa.html', {
        'qr_b64': qr_b64,
        'secret': secret,   # para mostrar la clave manual si el QR falla
    })


# ─────────────────────────────────────────────────────────────────────────────
# 2FA – Confirmar: validar el token y activar
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def confirmar_2fa(request):
    """
    Recibe el token de 6 dígitos, lo valida contra el secreto pendiente
    y, si es correcto, activa 2FA en la cuenta del usuario.
    """
    if request.method != 'POST':
        return redirect('setup-2fa')

    secret = request.session.get('totp_secret_pending')
    if not secret:
        messages.error(request, 'Sesión expirada. Reinicia la configuración de 2FA.')
        return redirect('setup-2fa')

    token = request.POST.get('token', '').strip()
    totp  = pyotp.TOTP(secret)

    if totp.verify(token, valid_window=1):
        user = request.user
        user.totp_secret  = secret
        user.totp_enabled = True
        user.save(update_fields=['totp_secret', 'totp_enabled'])
        del request.session['totp_secret_pending']
        # Generar 10 códigos de recuperación automáticamente
        generate_backup_codes(user, cantidad=10)
        messages.success(request, '✅ 2FA activado. Guarda tus códigos de recuperación en un lugar seguro.')
        return redirect('codigos-recuperacion')
    else:
        messages.error(request, 'Código incorrecto. Asegúrate de que el reloj de tu dispositivo esté sincronizado.')
        return redirect('setup-2fa')


# ─────────────────────────────────────────────────────────────────────────────
# 2FA – Desactivar
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def desactivar_2fa(request):
    """
    Desactiva 2FA en la cuenta del usuario.
    Acepta:
      - Código de 6 dígitos de Authy (TOTP)
      - Código de recuperación (XXXX-XXXX) si se perdió el celular
    """
    if request.method != 'POST':
        return redirect('configuracion-index')

    user  = request.user
    token = request.POST.get('token', '').strip().upper()

    if not user.totp_enabled:
        messages.error(request, '2FA no está activado en tu cuenta.')
        return redirect('configuracion-index')

    autenticado = False

    # ── 1. Intentar TOTP (Authy) ──────────────────────────────────────────────
    totp = pyotp.TOTP(user.totp_secret)
    if totp.verify(token, valid_window=1):
        autenticado = True
    else:
        # ── 2. Intentar código de recuperación ────────────────────────────────
        from django.utils import timezone as _tz
        # Normalizar sin guión → XXXX-XXXX
        if len(token) == 8 and '-' not in token:
            token = f"{token[:4]}-{token[4:]}"
        try:
            backup = BackupCode.objects.get(user=user, code=token, used=False)
            backup.used    = True
            backup.used_at = _tz.now()
            backup.save(update_fields=['used', 'used_at'])
            autenticado = True
        except BackupCode.DoesNotExist:
            pass

    if autenticado:
        user.totp_secret  = None
        user.totp_enabled = False
        user.save(update_fields=['totp_secret', 'totp_enabled'])
        # Eliminar todos los backup codes restantes
        BackupCode.objects.filter(user=user).delete()
        messages.success(request, '✅ 2FA desactivado. Puedes volver a activarlo cuando tengas tu nuevo dispositivo.')
    else:
        messages.error(request, '❌ Código incorrecto. Usa tu código de Authy o uno de tus códigos de recuperación.')

    return redirect('configuracion-index')


# ─────────────────────────────────────────────────────────────────────────────
# Backup Codes – Ver códigos de recuperación
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def ver_codigos_recuperacion(request):
    """Muestra los 10 códigos de recuperación del usuario."""
    user = request.user
    if not user.totp_enabled:
        messages.error(request, 'Debes activar 2FA primero.')
        return redirect('configuracion-index')

    codigos = BackupCode.objects.filter(user=user)
    disponibles = codigos.filter(used=False).count()
    return render(request, 'configuracion/codigos_recuperacion.html', {
        'codigos': codigos,
        'disponibles': disponibles,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Backup Codes – Regenerar
# ─────────────────────────────────────────────────────────────────────────────
@login_required
def regenerar_codigos(request):
    """Destruye los códigos actuales y genera 10 nuevos."""
    if request.method != 'POST':
        return redirect('codigos-recuperacion')

    user = request.user
    if not user.totp_enabled:
        messages.error(request, 'Debes activar 2FA primero.')
        return redirect('configuracion-index')

    generate_backup_codes(user, cantidad=10)
    messages.success(request, '🔑 Se generaron 10 nuevos códigos de recuperación. Los anteriores ya no son válidos.')
    return redirect('codigos-recuperacion')
