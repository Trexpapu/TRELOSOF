from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete
from django.core.cache import cache
from proveedores.models import Proveedores

CACHE_KEY_PROVEEDORES = 'lista_todos_proveedores'

@receiver(post_save, sender=Proveedores)
@receiver(post_delete, sender=Proveedores)
def invalidar_cache_proveedores(sender, instance, **kwargs):
    """
    Invalida el caché de la lista de proveedores cuando se crea, actualiza
    o elimina un proveedor.
    """
    cache.delete(CACHE_KEY_PROVEEDORES)
