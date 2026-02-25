from decimal import Decimal
from django.utils import timezone

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from cartera.models import Movimientos_Cartera
from facturas.models import FacturasFechasDePago
from cartera.services.movimiento_ajustes import eliminar_ajuste

# ============================================================
# SERVICIOS DE CÁLCULO (HELPERS)
# ============================================================

def servicio_obtener_monto_restante_por_pagar_factura(factura):
    total_pagado = (
        Movimientos_Cartera.objects
        .filter(factura=factura, origen="PAGO")
        .aggregate(total=Sum('monto'))['total']
        or Decimal('0.00')
    )
    return factura.monto - total_pagado


def servicio_obtener_monto_restante_por_pagar_factura_edicion(movimiento):
    factura = movimiento.factura
    total_pagado = (
        Movimientos_Cartera.objects
        .filter(factura=factura, origen="PAGO")
        .exclude(id=movimiento.pk)
        .aggregate(total=Sum('monto'))['total']
        or Decimal('0.00')
    )
    return factura.monto - total_pagado


# ============================================================
# SERVICIOS DE CONSULTA
# ============================================================

def servicio_obtener_movimientos(filters=None, user=None):
    if not user or not user.organizacion:
        return Movimientos_Cartera.objects.none()

    queryset = Movimientos_Cartera.objects.filter(organizacion=user.organizacion).select_related(
        'factura', 
        'fecha_pago_instancia',
        'venta'
    ).order_by('-fecha')

    has_active_filters = False

    if filters:
        if filters.get('fecha_inicio'):
            queryset = queryset.filter(fecha__gte=filters['fecha_inicio'])
            has_active_filters = True

        if filters.get('fecha_fin'):
            queryset = queryset.filter(fecha__lte=filters['fecha_fin'])
            has_active_filters = True

        if filters.get('origen'):
            queryset = queryset.filter(origen=filters['origen'])
            has_active_filters = True

        if filters.get('sucursal'):
            queryset = queryset.filter(venta__sucursal_id=filters['sucursal'])
            has_active_filters = True

        if filters.get('folio'):
            queryset = queryset.filter(factura__folio__icontains=filters['folio'])
            has_active_filters = True

    # Si no se aplicó ningún filtro, limitamos a 20 resultados
    if not has_active_filters:
        return queryset[:20]

    return queryset


# ============================================================
# SERVICIOS DE CREACIÓN
# ============================================================

@transaction.atomic
def registrar_movimiento_pago_factura(data, user):
    factura = data.get('factura')
    monto = data.get('monto')

    if not factura:
        raise ValidationError('Factura requerida.')
        
    if factura.organizacion != user.organizacion:
        raise ValidationError('No tienes permiso para pagar esta factura.')

    if factura.estado == "PAGADO":
        raise ValidationError('Esta factura ya está pagada.')

    if monto <= 0:
        raise ValidationError('El monto debe ser mayor a cero.')

    monto_restante = servicio_obtener_monto_restante_por_pagar_factura(factura)

    if monto > monto_restante: 
        raise ValidationError(
            'El monto no puede exceder el total restante por pagar.'
        )

    fecha_movimiento = data.get('fecha', timezone.now().date())

    movimiento = Movimientos_Cartera.objects.create(
        origen="PAGO",
        monto=monto,
        factura=factura,
        descripcion=f'Pago de factura con FOLIO {factura.folio}',
        fecha=fecha_movimiento,
        organizacion=factura.organizacion
    )

    if monto == monto_restante:
        factura.estado = "PAGADO"
    else:
        factura.estado = "ABONADO"

    factura.save(update_fields=['estado'])

    return movimiento


# ============================================================
# SERVICIOS DE EDICIÓN
# ============================================================

@transaction.atomic
def servicio_editar_movimiento_pago_factura(movimiento, data, user):
    if movimiento.organizacion != user.organizacion:
         raise ValidationError('No tienes permiso para editar este movimiento.')

    if movimiento.origen != "PAGO":
        raise ValidationError('Solo se pueden editar pagos')

    monto = data.get('monto')
    factura = movimiento.factura

    if monto <= 0:
        raise ValidationError('El monto debe ser mayor a cero.')

    monto_restante_posible = (
        servicio_obtener_monto_restante_por_pagar_factura_edicion(movimiento)
    )

    if monto > monto_restante_posible:
        raise ValidationError(
            'El monto no puede exceder el total restante por pagar.'
        )

    if monto == monto_restante_posible:
        factura.estado = "PAGADO"
    else:
        factura.estado = "ABONADO"

    movimiento.monto = monto
    movimiento.save()
    factura.save(update_fields=['estado'])


# ============================================================
# SERVICIOS DE ELIMINACIÓN
# ============================================================

@transaction.atomic
def servicio_eliminar_movimiento_pago_factura(movimiento, user):
    if movimiento.organizacion != user.organizacion:
         raise ValidationError('No tienes permiso para eliminar este movimiento.')

    if movimiento.origen == "AJUSTE_SUMA" or movimiento.origen == "AJUSTE_RESTA":
        eliminar_ajuste(movimiento, user)
        return

    if movimiento.origen != "PAGO":
        raise ValidationError('Solo se pueden eliminar pagos o ajustes')

    factura = movimiento.factura

    if not Movimientos_Cartera.objects.filter(pk=movimiento.pk).exists():
        raise ValidationError('Movimiento no encontrado.')

    movimiento.delete()

    monto_restante = servicio_obtener_monto_restante_por_pagar_factura(factura)

    if monto_restante == factura.monto:
        factura.estado = "PENDIENTE"
    else:
        factura.estado = "ABONADO"

    factura.save(update_fields=['estado'])


# ============================================================
# SERVICIOS DE PAGO MASIVO
# ============================================================

@transaction.atomic
def servicio_pagar_facturas_masivas(fechas_ids, fecha_pago=None, user=None):
    """
    Procesa el pago masivo. Filtra por organización.
    """
    reporte = {
        'pagadas': 0,
        'omitidas': 0,
        'errores': 0,
        'monto_total': Decimal('0.00'),
        'detalles': []
    }

    if not fechas_ids or not user or not user.organizacion:
        return reporte

    # Filtramos solo las fechas válidas existentes DE LA ORGANIZACIÓN
    fechas_pago_qs = FacturasFechasDePago.objects.filter(
        id__in=fechas_ids,
        factura__organizacion=user.organizacion 
    ).select_related('factura')

    for item_fecha_pago in fechas_pago_qs:
        factura = item_fecha_pago.factura

        if factura.estado == 'PAGADO':
            reporte['omitidas'] += 1
            reporte['detalles'].append(f'Factura {factura.folio} ya pagada. Omitida.')
            continue

        monto_restante_factura = servicio_obtener_monto_restante_por_pagar_factura(factura)

        if monto_restante_factura <= 0:
            reporte['omitidas'] += 1
            continue

        monto_a_pagar = min(item_fecha_pago.monto_por_pagar, monto_restante_factura)
        
        if monto_a_pagar <= 0:
            reporte['omitidas'] += 1
            continue

        try:
            data = {
                'factura': factura,
                'monto': monto_a_pagar,
                'fecha': fecha_pago or timezone.now().date()
            }
            # Reutilizamos registro de pago que ya valida organización y asigna
            registrar_movimiento_pago_factura(data, user)
            
            reporte['pagadas'] += 1
            reporte['monto_total'] += monto_a_pagar
            
        except ValidationError as e:
            reporte['errores'] += 1
            reporte['detalles'].append(f'Error en factura {factura.folio}: {str(e)}')
        except Exception as e:
            reporte['errores'] += 1
            reporte['detalles'].append(f'Error inesperado en factura {factura.folio}: {str(e)}')

    return reporte
