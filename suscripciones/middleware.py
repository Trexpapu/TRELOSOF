"""
SuscripcionMiddleware
─────────────────────
Intercepta CADA request de un usuario autenticado y verifica que su
organización tenga una suscripción activa (TRIAL o ACTIVA).

Reglas de bloqueo:
  TRIAL    → NUNCA bloquear
  ACTIVA   → NUNCA bloquear
  VENCIDA  → SIEMPRE bloquear (trial venció sin pagar)
  CANCELADA → respetar el período ya pagado:
               · proximo_cobro > ahora → ya pagó ese mes → acceso libre
               · proximo_cobro <= ahora o None → bloquear

Cuando bloquea, redirige de forma inteligente:
  · Tiene tarjeta guardada → /suscripcion/historial/ (puede pagar ahora)
  · Sin tarjeta            → /suscripcion/metodo-pago/ (agrega tarjeta primero)

URLs siempre accesibles (whitelist):
  /login/  /logout/
  /suscripcion/metodo-pago/
  /suscripcion/historial/
  /suscripcion/cobrar/
  /suscripcion/cancelar/
  /static/  /media/  /admin/
"""

from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone


WHITELIST_PREFIXES = (
    '/login/',
    '/logout/',
    '/2fa/verificar/',             # paso 2 del login con 2FA
    '/suscripcion/metodo-pago/',
    '/suscripcion/historial/',
    '/suscripcion/cobrar/',
    '/suscripcion/cancelar/',
    '/core/terminos-y-condiciones/',
    '/core/politicas-de-privacidad/',
    '/static/',
    '/media/',
    '/admin/',
)


class SuscripcionMiddleware:
    """
    Se ejecuta DESPUÉS de AuthenticationMiddleware, por lo que
    request.user ya está disponible.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            path = request.path
            if not any(path.startswith(prefix) for prefix in WHITELIST_PREFIXES):
                suscripcion = self._obtener_suscripcion(request.user)
                if suscripcion and self._debe_bloquear(suscripcion):
                    if suscripcion.tiene_metodo_pago:
                        return redirect(reverse('suscripcion-historial'))
                    else:
                        return redirect(reverse('suscripcion-metodo-pago'))

        return self.get_response(request)

    @staticmethod
    def _debe_bloquear(suscripcion):
        """
        VENCIDA              → bloquear siempre.
        CANCELADA + crédito  → NO bloquear (período ya pagado vigente).
        CANCELADA sin crédito → bloquear.
        TRIAL / ACTIVA       → nunca bloquear.
        """
        if suscripcion.estado == 'VENCIDA':
            return True

        if suscripcion.estado == 'CANCELADA':
            # Si todavía tiene período pagado vigente → dejar pasar
            if suscripcion.proximo_cobro and suscripcion.proximo_cobro > timezone.now():
                return False
            return True  # Período vencido → bloquear

        return False  # TRIAL o ACTIVA

    @staticmethod
    def _obtener_suscripcion(user):
        try:
            return user.organizacion.suscripcion
        except Exception:
            return None
