from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from cartera.models import Movimientos_Cartera

@transaction.atomic
def servicio_crear_movimiento_ingreso(venta):
    # Obtenemos la organización de la sucursal de la venta
    if not venta.sucursal or not venta.sucursal.organizacion:
        raise ValidationError("La sucursal de la venta no tiene organización asignada.")
        
    return Movimientos_Cartera.objects.create(
        origen='INGRESO',
        monto=venta.monto,
        descripcion=f'Ingreso ${venta.monto} de sucursal {venta.sucursal.nombre}',
        venta=venta,
        fecha=venta.fecha,
        organizacion=venta.sucursal.organizacion
    )
    
@transaction.atomic
def servicio_editar_movimiento_ingreso(venta):
    movimiento = Movimientos_Cartera.objects.get(venta=venta)

    # Validamos que la organización coincida
    if movimiento.organizacion != venta.sucursal.organizacion:
         # Si cambiaron la sucursal de la venta a una de otra org (poco probable pero posible), actualizamos
         movimiento.organizacion = venta.sucursal.organizacion
         
    movimiento.monto = venta.monto
    movimiento.fecha = venta.fecha
    movimiento.descripcion = f'Actualiza Ingreso ${venta.monto} de sucursal {venta.sucursal.nombre}'
    movimiento.save()
    return movimiento

@transaction.atomic
def servicio_eliminar_movimiento_ingreso(venta):
    """Elimina todos los movimiento de ingreso asociado a la venta"""
    Movimientos_Cartera.objects.filter(venta=venta).delete()
