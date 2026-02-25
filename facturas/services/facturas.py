
from django.core.exceptions import ValidationError
from django.db import transaction
from facturas.models import Facturas, FacturasFechasDePago
from cartera.services.movimientos_cargo import registrar_movimiento_crear_factura, actualizar_movimiento_factura, eliminar_movimientos_factura
from datetime import datetime
from decimal import Decimal

@transaction.atomic
def servicio_crear_factura_con_fechas(data, user):
    """
    Crear factura con contexto de organizacion.
    """
    organizacion = user.organizacion
    if not organizacion:
        raise ValidationError("El usuario no pertenece a ninguna organización.")

    factura_data = data.get('factura')
    pagos_data = data.get('pagos')

    if not factura_data:
        raise ValidationError('Datos de factura requeridos.')

    if not pagos_data:
        raise ValidationError('Debe registrar al menos un pago.')
    
    # Validamos que el proveedor pertenezca a la organización
    proveedor = factura_data['proveedor']
    if proveedor.organizacion != organizacion:
        raise ValidationError("El proveedor seleccionado no pertenece a tu organización.")

    folio = factura_data.get('folio')
    # Validamos folio único POR ORGANIZACIÓN
    if Facturas.objects.filter(folio=folio, organizacion=organizacion).exists():
        raise ValidationError('Ya existe una factura con el folio proporcionado en tu organización.')

    fechas = []
    montos = []

    for p in pagos_data:
        fechas.append(p['fecha'])
        montos.append(Decimal(p['monto']))

    monto_total = Decimal(factura_data['monto'])
    suma_montos = sum(montos)

    if abs(suma_montos - monto_total) > Decimal('0.01'):
        raise ValidationError(
            f'La suma de los pagos ({suma_montos:.2f}) '
            f'no coincide con el total de la factura ({monto_total:.2f}).'
        )

    factura = Facturas.objects.create(
        proveedor=proveedor,
        folio=folio,
        tipo=factura_data['tipo'],
        monto=monto_total,
        notas=factura_data.get('notas', ''),
        estado='PENDIENTE',
        organizacion=organizacion,
        cuenta_override=factura_data.get('cuenta_override', 'PROVEEDOR'),
    )

    FacturasFechasDePago.objects.bulk_create([
        FacturasFechasDePago(
            factura=factura,
            fecha_por_pagar=p['fecha'],
            monto_por_pagar=p['monto']
        )
        for p in pagos_data
    ])

    registrar_movimiento_crear_factura(factura)

    return factura


@transaction.atomic
def servicio_editar_factura(factura, data, user):
    if factura.organizacion != user.organizacion:
        raise ValidationError("No tienes permiso para editar esta factura.")

    # Obtener la instancia original de la BD 
    factura_orig = Facturas.objects.get(pk=factura.pk)
    
    # Validamos proveedor
    proveedor = data['proveedor']
    if proveedor.organizacion != user.organizacion:
        raise ValidationError("El proveedor seleccionado no pertenece a tu organización.")

    if factura_orig.estado != "PENDIENTE":
        if factura_orig.monto != data['monto']:
            raise ValidationError("No se puede editar el monto de una factura que ya ha sido pagada o abonada.")
    
    factura.proveedor = proveedor
    factura.folio = data.get('folio')
    factura.tipo = data['tipo']
    factura.monto = data['monto']
    factura.notas = data.get('notas', '')
    factura.cuenta_override = data.get('cuenta_override', 'AUTO')
    factura.save()

    if factura_orig.estado == 'PENDIENTE' and 'fechas_pago' in data and 'montos_pago' in data:
        fechas = data['fechas_pago']
        montos = data['montos_pago']
        monto_total = factura.monto 

        if len(fechas) != len(montos):
             raise ValidationError(f'Discrepancia entre fechas ({len(fechas)}) y montos ({len(montos)}).')

        suma_montos = sum(montos)
        if abs(suma_montos - monto_total) > Decimal('0.01'):
            raise ValidationError(
                f'La suma de los pagos ({suma_montos:.2f}) '
                f'no coincide con el total de la factura ({monto_total:.2f}).'
            )

        FacturasFechasDePago.objects.filter(factura=factura).delete()
        
        FacturasFechasDePago.objects.bulk_create([
            FacturasFechasDePago(
                factura=factura,
                fecha_por_pagar=fecha,
                monto_por_pagar=monto
            )
            for fecha, monto in zip(fechas, montos)
        ])

    actualizar_movimiento_factura(factura)
    return factura
    


@transaction.atomic
def servicio_eliminar_factura(factura, user):
    if factura.organizacion != user.organizacion:
        raise ValidationError("No tienes permiso para eliminar esta factura.")
        
    eliminar_movimientos_factura(factura)
    factura.delete()


def servicio_obtener_facturas(filters=None, user=None):
    if not user or not user.organizacion:
        return Facturas.objects.none()

    queryset = Facturas.objects.filter(organizacion=user.organizacion)\
        .select_related('proveedor')\
        .prefetch_related('facturasfechasdepago_set')\
        .order_by('estado', 'folio')

    if filters:
        if filters.get('folio'):
            queryset = queryset.filter(folio__icontains=filters['folio'])
        
        if filters.get('proveedor'):
            queryset = queryset.filter(proveedor_id=filters['proveedor'])
            
        if filters.get('estado'):
            queryset = queryset.filter(estado=filters['estado'])

        if filters.get('tipo'):
            queryset = queryset.filter(tipo=filters['tipo'])

    else:
        queryset = queryset[:50]

    return queryset
