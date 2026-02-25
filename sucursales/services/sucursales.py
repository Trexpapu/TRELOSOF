# services.py
from django.core.exceptions import ValidationError
from django.db import transaction

from sucursales.models import Sucursales


def servicio_listar_sucursales(user):
    if not user.organizacion:
        return []
    return Sucursales.objects.filter(organizacion=user.organizacion).order_by('nombre')


@transaction.atomic
def servicio_crear_sucursal(data, user):
    if not user.organizacion:
        raise ValidationError("El usuario no pertenece a ninguna organización.")
        
    return Sucursales.objects.create(
        nombre=data['nombre'],
        direccion=data.get('direccion', ''),
        organizacion=user.organizacion
    )


@transaction.atomic
def servicio_editar_sucursal(sucursal, data, user):
    if sucursal.organizacion != user.organizacion:
        raise ValidationError("No tienes permiso para editar esta sucursal.")
        
    sucursal.nombre = data['nombre']
    sucursal.direccion = data.get('direccion', '')
    sucursal.save(update_fields=['nombre', 'direccion'])
    return sucursal


@transaction.atomic
def servicio_eliminar_sucursal(sucursal, user):
    if not sucursal.pk:
        raise ValidationError('Sucursal no encontrada.')
        
    if sucursal.organizacion != user.organizacion:
        raise ValidationError("No tienes permiso para eliminar esta sucursal.")
        
    sucursal.delete()
