"""
Management command: procesar_cobros

Uso normal (cron diario):
  python manage.py procesar_cobros

Simular una fecha futura para testing:
  python manage.py procesar_cobros --fecha 2026-03-25
  python manage.py procesar_cobros --fecha 2026-05-25

Qué hace:
  1. Busca suscripciones TRIAL cuyo trial_fin <= FECHA_REFERENCIA
     → Si tiene método de pago: cobra y activa
     → Si no tiene PM: marca como VENCIDA
  2. Busca suscripciones ACTIVAS cuyo proximo_cobro <= FECHA_REFERENCIA
     → Cobra mensualmente (respeta meses anticipados)
"""

import logging
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.core.exceptions import ValidationError

from suscripciones.models import Suscripcion
from suscripciones.services.suscripcion import ejecutar_cobro

logger = logging.getLogger('suscripciones')


class Command(BaseCommand):
    help = 'Procesa cobros vencidos. Usa --fecha YYYY-MM-DD para simular una fecha.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fecha',
            type=str,
            default=None,
            help='Fecha a simular en formato YYYY-MM-DD (ej: 2026-03-25). '
                 'Sin este argumento usa la fecha real de hoy.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Solo muestra qué se cobraría sin ejecutar ningún cobro real.',
        )

    def handle(self, *args, **options):
        # ── Determinar la fecha de referencia ─────────────────────────────────
        fecha_str = options.get('fecha')
        dry_run   = options.get('dry_run')

        if fecha_str:
            try:
                fecha_naive = datetime.strptime(fecha_str, '%Y-%m-%d')
                ahora = timezone.make_aware(fecha_naive)
                self.stdout.write(self.style.WARNING(
                    f'\n[!] MODO SIMULACION - Fecha ficticia: {fecha_str}'
                ))
            except ValueError:
                raise CommandError(f"Formato de fecha invalido: '{fecha_str}'. Usa YYYY-MM-DD.")
        else:
            ahora = timezone.now()
            self.stdout.write(f'\nFecha real: {ahora.strftime("%Y-%m-%d %H:%M")}')

        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY RUN] Solo lectura - sin cobros reales\n'))

        self.stdout.write('-' * 60)

        procesados = 0
        errores    = 0
        omitidos   = 0

        # -- 1. Trials vencidos -----------------------------------------------
        trials_vencidos = Suscripcion.objects.filter(
            estado='TRIAL',
            trial_fin__lte=ahora,
        ).select_related('organizacion')

        self.stdout.write(f'\n[TRIAL] Suscripciones de trial vencidas: {trials_vencidos.count()}')

        for sub in trials_vencidos:
            org = sub.organizacion.nombre
            self.stdout.write(f'\n  Org: {org}')
            self.stdout.write(f'    Estado:    TRIAL vencido el {sub.trial_fin.strftime("%d/%m/%Y")}')
            self.stdout.write(f'    Tiene PM:  {"Si (" + sub.card_brand + " ****" + sub.card_last4 + ")" if sub.tiene_metodo_pago else "No"}')

            if sub.tiene_metodo_pago:
                self.stdout.write(f'    Accion:    Cobrar ${sub.precio_mensual} MXN')
                if not dry_run:
                    try:
                        ejecutar_cobro(sub)
                        sub.refresh_from_db()
                        procesados += 1
                        self.stdout.write(self.style.SUCCESS(
                            f'    [OK] Cobro exitoso -> ACTIVA | Proximo cobro: {sub.proximo_cobro.strftime("%d/%m/%Y")}'
                        ))
                    except ValidationError as e:
                        errores += 1
                        self.stdout.write(self.style.ERROR(f'    [FAIL] Cobro fallido: {e}'))
                else:
                    self.stdout.write(self.style.WARNING('    -> [DRY RUN] Se cobraria aqui'))
                    omitidos += 1
            else:
                self.stdout.write(f'    Accion:    Sin PM -> marcar VENCIDA')
                if not dry_run:
                    sub.estado = 'VENCIDA'
                    sub.save(update_fields=['estado', 'updated_at'])
                    self.stdout.write(self.style.WARNING(f'    [!] Marcada como VENCIDA'))
                else:
                    self.stdout.write(self.style.WARNING('    -> [DRY RUN] Se marcaria VENCIDA'))
                    omitidos += 1

        # -- 2. Cobros mensuales vencidos --------------------------------------
        cobros_mensuales = Suscripcion.objects.filter(
            estado='ACTIVA',
            proximo_cobro__lte=ahora,
        ).select_related('organizacion')

        self.stdout.write(f'\n[MENSUAL] Cobros mensuales vencidos: {cobros_mensuales.count()}')

        for sub in cobros_mensuales:
            org = sub.organizacion.nombre
            self.stdout.write(f'\n  Org: {org}')
            self.stdout.write(f'    Proximo cobro era: {sub.proximo_cobro.strftime("%d/%m/%Y")}')
            self.stdout.write(f'    Monto:             ${sub.precio_mensual} MXN')

            # Calcular dias cubiertos RESPECTO A LA FECHA SIMULADA (no timezone.now() real)
            # El filtro SQL ya garantiza proximo_cobro <= ahora, pero lo verificamos
            # también para mostrar info correcta en el log.
            desde_ahora = (sub.proximo_cobro - ahora).days if sub.proximo_cobro else -1
            from django.conf import settings as dj_settings
            ciclo = getattr(dj_settings, 'SUSCRIPCION_CICLO_DIAS', 30)
            meses_sim = max(int((- desde_ahora) / ciclo), 0) if desde_ahora < 0 else 0

            self.stdout.write(f'    Atraso en dias:    {abs(desde_ahora)} dia(s) vencido(s)')

            if not dry_run:
                try:
                    ejecutar_cobro(sub)
                    sub.refresh_from_db()
                    procesados += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'    [OK] Cobro exitoso | Nuevo proximo cobro: {sub.proximo_cobro.strftime("%d/%m/%Y")}'
                    ))
                except ValidationError as e:
                    errores += 1
                    self.stdout.write(self.style.ERROR(f'    [FAIL] Cobro fallido: {e}'))
            else:
                self.stdout.write(self.style.WARNING('    -> [DRY RUN] Se cobraria aqui'))
                omitidos += 1

        # -- Resumen ----------------------------------------------------------
        self.stdout.write('\n' + '-' * 60)
        self.stdout.write(
            self.style.SUCCESS(
                f'Procesamiento terminado:\n'
                f'   Exitosos: {procesados}\n'
                f'   Errores:  {errores}\n'
                f'   Omitidos: {omitidos}\n'
            )
        )
