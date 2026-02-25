from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import User, Organizacion

# Aquí puedes poner lógica adicional que se dispare tras crear Usuario u Organización.
# Por ejemplo, enviar un correo de bienvenida, generar logs, crear configuración default, etc.

@receiver(post_save, sender=Organizacion)
def organizacion_created_handler(sender, instance, created, **kwargs):
    if created:
        print(f"Nueva organización creada: {instance.nombre}")
        # Lógica adicional: Crear configuración inicial, plan gratuito, etc.

@receiver(post_save, sender=User)
def user_created_handler(sender, instance, created, **kwargs):
    if created:
        print(f"Nuevo usuario creado: {instance.email} en {instance.organizacion}")
        # Lógica adicional: Logs de auditoría.
