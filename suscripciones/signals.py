"""
Signals for the suscripciones app.

post_save on Organizacion → crea automáticamente la suscripción TRIAL.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from users.models import Organizacion
from .services.suscripcion import crear_suscripcion_trial


@receiver(post_save, sender=Organizacion)
def crear_trial_al_crear_organizacion(sender, instance, created, **kwargs):
    """
    Cuando se crea una nueva organización, dispara automáticamente
    la creación del período de prueba de 14 días.
    """
    if created:
        crear_suscripcion_trial(instance)
