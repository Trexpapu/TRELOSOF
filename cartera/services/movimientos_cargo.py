from decimal import Decimal
from django.utils import timezone

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from cartera.models import Movimientos_Cartera


@transaction.atomic
def registrar_movimiento_crear_factura(factura):
    fechas_pago = factura.facturasfechasdepago_set.all()
    movimientos = []
    
    # Obtenemos la organización de la factura
    organizacion = factura.organizacion
    if not organizacion:
        raise ValidationError("La factura no tiene organización asignada.")

    if not fechas_pago.exists():
        # Fallback for legacy or edge cases
        Movimientos_Cartera.objects.create(
            origen='CARGO',
            monto=factura.monto,
            descripcion=f'Creación de factura con FOLIO {factura.folio}',
            factura=factura,
            fecha=timezone.now().date(),
            organizacion=organizacion
        )
        return

    for fecha_instancia in fechas_pago:
        movimientos.append(Movimientos_Cartera(
            origen='CARGO',
            monto=fecha_instancia.monto_por_pagar,
            descripcion=f'Creación de factura con FOLIO {factura.folio} - Cuota {fecha_instancia.fecha_por_pagar}',
            factura=factura,
            fecha=fecha_instancia.fecha_por_pagar,
            fecha_pago_instancia=fecha_instancia,
            organizacion=organizacion
        ))
    
    Movimientos_Cartera.objects.bulk_create(movimientos)


@transaction.atomic
def actualizar_movimiento_factura(factura):
    # CRITICAL: Only delete CARGO movements. Protect PAGOS and INGRESOS.
    Movimientos_Cartera.objects.filter(
        factura=factura,
        origen='CARGO'
    ).delete()

    # Re-create movements based on current payment schedules
    registrar_movimiento_crear_factura(factura)


@transaction.atomic
def eliminar_movimientos_factura(factura):
    """
    Elimina todos los movimientos asociados a una factura.
    """
    Movimientos_Cartera.objects.filter(factura=factura).delete()
