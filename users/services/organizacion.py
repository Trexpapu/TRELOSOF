from django.db import transaction
from django.core.exceptions import ValidationError
from ..models import Organizacion


@transaction.atomic
def servicio_editar_organizacion(organizacion, data, user):
    """
    Edita el nombre de la organización.
    Solo el admin de la organización puede hacer esto.
    """
    if not user.is_organizacion_admin:
        raise ValidationError("Solo el administrador puede editar la organización.")

    if organizacion != user.organizacion:
        raise ValidationError("No tienes permiso para editar esta organización.")

    nuevo_nombre = data.get('nombre', '').strip()
    if not nuevo_nombre:
        raise ValidationError("El nombre de la organización no puede estar vacío.")

    # Verificar que no exista otra org con ese nombre
    if Organizacion.objects.filter(nombre=nuevo_nombre).exclude(pk=organizacion.pk).exists():
        raise ValidationError("Ya existe una organización con ese nombre.")

    organizacion.nombre = nuevo_nombre
    organizacion.save(update_fields=['nombre'])
    return organizacion
