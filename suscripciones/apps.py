from django.apps import AppConfig


class SuscripcionesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'suscripciones'
    verbose_name = 'Suscripciones'

    def ready(self):
        import suscripciones.signals  # noqa: F401 – conecta los signals al arrancar
