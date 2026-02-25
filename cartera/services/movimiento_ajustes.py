from django.db import transaction
from django.core.exceptions import ValidationError
from ..models import Movimientos_Cartera

@transaction.atomic
def crear_ajuste(monto, tipo_ajuste, descripcion=None, fecha=None, user=None):
    """
    Crea un movimiento de ajuste (SUMA o RESTA).
    """
    if not user or not user.organizacion:
        raise ValidationError("El usuario no pertenece a ninguna organización.")
    
    origen = ''
    if tipo_ajuste == 'SUMAR':
        origen = 'AJUSTE_SUMA'
        desc_prefix = 'Ajuste (Suma)'
    elif tipo_ajuste == 'RESTAR':
        origen = 'AJUSTE_RESTA'
        desc_prefix = 'Ajuste (Resta)'
    else:
        raise ValueError("Tipo de ajuste inválido. Debe ser 'SUMAR' o 'RESTAR'.")
    
    if not descripcion:
        descripcion = f"{desc_prefix}: ${monto}"
    
    movimiento_args = {
        'origen': origen,
        'monto': monto,
        'descripcion': descripcion,
        'organizacion': user.organizacion # Asignamos la organización
    }
    
    if fecha:
        movimiento_args['fecha'] = fecha
    
    movimiento = Movimientos_Cartera.objects.create(**movimiento_args)
    
    return movimiento


@transaction.atomic
def eliminar_ajuste(movimiento, user):
    if movimiento.organizacion != user.organizacion:
        raise ValidationError("No tienes permiso para eliminar este ajuste.")
    movimiento.delete()
