from django.db import transaction
from django.core.exceptions import ValidationError
from ..models import Proveedores
from django.core.cache import cache


def _invalidar_cache_proveedores(organizacion):
    """Invalida el caché de la lista de proveedores para la organzación dada."""
    cache.delete(f'lista_proveedores_org_{organizacion.id}')


@transaction.atomic
def servicio_crear_proveedor(data, user):
    organizacion = user.organizacion
    if not organizacion:
        raise ValidationError("El usuario no pertenece a ninguna organización.")

    # Regla de negocio: Validar teléfono único POR ORGANIZACIÓN
    if data.get('telefono'):
        if Proveedores.objects.filter(
            telefono__iexact=data['telefono'],
            organizacion=organizacion
        ).exists():
            raise ValidationError('Ya existe un proveedor con ese teléfono en tu organización.')

    CAMPOS_PERMITIDOS = (
        'nombre',
        'cuenta',
        'telefono',
        'email',
        'cuenta_maestra',
    )

    payload = {
        campo: data[campo]
        for campo in CAMPOS_PERMITIDOS
        if campo in data
    }
    
    # Asignar organización automáticamente
    payload['organizacion'] = organizacion

    proveedor = Proveedores.objects.create(**payload)
    _invalidar_cache_proveedores(organizacion)   # <-- invalida caché
    return proveedor


@transaction.atomic
def servicio_editar_proveedor(proveedor, data, user):
    if proveedor.organizacion != user.organizacion:
        raise ValidationError("No tienes permiso para editar este proveedor.")

    CAMPOS_EDITABLES = (
        'nombre',
        'cuenta',
        'telefono',
        'email',
        'cuenta_maestra',
    )

    # Validación de negocio SOLO si cambia el teléfono
    if 'telefono' in data:
        if Proveedores.objects.filter(
            telefono__iexact=data['telefono'],
            organizacion=user.organizacion
        ).exclude(pk=proveedor.pk).exists():
            raise ValidationError('Ya existe un proveedor con ese teléfono en tu organización.')

    for campo in CAMPOS_EDITABLES:
        if campo in data:
            setattr(proveedor, campo, data[campo])

    proveedor.save()
    _invalidar_cache_proveedores(user.organizacion)  # <-- invalida caché
    return proveedor


def servicio_obtener_proveedores(filters=None, user=None):
    """
    Punto único de obtención de proveedores por organización.
    """
    if not user or not user.organizacion:
        return []

    org_id = user.organizacion.id
    CACHE_KEY = f'lista_proveedores_org_{org_id}'

    # 1. Intentar obtener la lista completa del caché
    todos_proveedores = cache.get(CACHE_KEY)

    if todos_proveedores is None:
        # Si no está en caché, consultar DB filtrando por organización
        todos_proveedores = list(Proveedores.objects.filter(organizacion=user.organizacion).order_by('nombre'))
        # Guardamos en caché por 24 horas
        cache.set(CACHE_KEY, todos_proveedores, timeout=60*60*24)

    # 2. Filtrado en Memoria
    resultado = todos_proveedores
    
    if filters:
        if filters.get('nombre'):
            val = filters['nombre'].lower()
            resultado = [p for p in resultado if val in p.nombre.lower()]
        
        if filters.get('telefono'):
            val = filters['telefono'].lower()
            resultado = [p for p in resultado if p.telefono and val in p.telefono.lower()]
            
        if filters.get('email'):
            val = filters['email'].lower()
            resultado = [p for p in resultado if p.email and val in p.email.lower()]
            
    return resultado


@transaction.atomic
def servicio_eliminar_proveedor(proveedor, user):
    if proveedor.organizacion != user.organizacion:
        raise ValidationError("No tienes permiso para eliminar este proveedor.")
    organizacion = proveedor.organizacion
    proveedor.delete()
    _invalidar_cache_proveedores(organizacion)   # <-- invalida caché
