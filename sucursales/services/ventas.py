from django.core.exceptions import ValidationError
from django.db import transaction
from datetime import date

from sucursales.models import Sucursales, Ventas
from cartera.services.movimientos_ingreso import (
    servicio_crear_movimiento_ingreso,
    servicio_editar_movimiento_ingreso,
    servicio_eliminar_movimiento_ingreso,
)


def servicio_listar_ventas(filters=None, user=None):
    """
    Devuelve las ventas de la organización del usuario aplicando
    filtros opcionales: sucursal, fecha_desde, fecha_hasta.
    """
    if not user or not user.organizacion:
        return Ventas.objects.none()

    qs = Ventas.objects.filter(
        sucursal__organizacion=user.organizacion
    ).select_related('sucursal').order_by('-fecha', '-id')

    if filters:
        if filters.get('sucursal'):
            qs = qs.filter(sucursal_id=filters['sucursal'])

        if filters.get('fecha_desde'):
            qs = qs.filter(fecha__gte=filters['fecha_desde'])

        if filters.get('fecha_hasta'):
            qs = qs.filter(fecha__lte=filters['fecha_hasta'])

    return qs


@transaction.atomic
def servicio_crear_venta(data, user):
    if data['monto'] <= 0:
        raise ValidationError('El monto debe ser mayor a cero.')

    sucursal = data['sucursal']
    if sucursal.organizacion != user.organizacion:
        raise ValidationError('La sucursal seleccionada no pertenece a tu organización.')

    venta = Ventas.objects.create(
        fecha=data['fecha'],
        monto=data['monto'],
        sucursal=sucursal
    )
    servicio_crear_movimiento_ingreso(venta)
    return venta


@transaction.atomic
def servicio_editar_venta(venta, data, user):
    if data['monto'] <= 0:
        raise ValidationError('El monto debe ser mayor a cero.')

    sucursal = data['sucursal']
    if sucursal.organizacion != user.organizacion:
        raise ValidationError('La sucursal seleccionada no pertenece a tu organización.')

    if venta.sucursal.organizacion != user.organizacion:
        raise ValidationError('No tienes permiso para editar esta venta.')

    venta.fecha = data['fecha']
    venta.monto = data['monto']
    venta.sucursal = sucursal
    venta.save()

    servicio_editar_movimiento_ingreso(venta)
    return venta


@transaction.atomic
def servicio_eliminar_venta(venta, user):
    if not venta:
        raise ValidationError('La venta no existe.')

    if venta.sucursal.organizacion != user.organizacion:
        raise ValidationError('No tienes permiso para eliminar esta venta.')

    servicio_eliminar_movimiento_ingreso(venta)
    venta.delete()
    return venta
