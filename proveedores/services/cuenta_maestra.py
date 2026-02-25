from django.db import transaction
from django.core.exceptions import ValidationError
from ..models import Cuenta_Maestra

@transaction.atomic
def servicio_crear_cuenta_maestra(data, user):
    organizacion = user.organizacion
    if not organizacion:
        raise ValidationError("El usuario no pertenece a ninguna organización.")

    if Cuenta_Maestra.objects.filter(organizacion=organizacion).exists():
        raise ValidationError('Ya existe una Cuenta Maestra registrada para tu organización.')

    CAMPOS_PERMITIDOS = (
        'nombre',
        'cuenta',
        'telefono',
        'email',
    )

    payload = {
        campo: data[campo]
        for campo in CAMPOS_PERMITIDOS
        if campo in data
    }
    
    payload['organizacion'] = organizacion

    cuenta = Cuenta_Maestra.objects.create(**payload)
    return cuenta


@transaction.atomic
def servicio_editar_cuenta_maestra(cuenta, data, user):
    if cuenta.organizacion != user.organizacion:
        raise ValidationError("No tienes permiso para editar esta cuenta maestra.")

    CAMPOS_EDITABLES = (
        'nombre',
        'cuenta',
        'telefono',
        'email',
    )

    for campo in CAMPOS_EDITABLES:
        if campo in data:
            setattr(cuenta, campo, data[campo])

    cuenta.save()
    return cuenta


def servicio_obtener_cuenta_maestra(user):
    """
    Obtiene la única instancia de Cuenta Maestra para la organización del usuario.
    Retorna None si no existe o el usuario no tiene org.
    """
    if not user or not user.organizacion:
        return None
        
    return Cuenta_Maestra.objects.filter(organizacion=user.organizacion).first()
