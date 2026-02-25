from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
import secrets, string

# --- MODELO DE ORGANIZACIÓN ---
class Organizacion(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre


# --- MANAGER DE USUARIO ---
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("El usuario debe tener un correo electrónico")
        
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """ Requerido por Django para comandos de consola """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


# --- MODELO DE USUARIO PERSONALIZADO ---
class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    
    # Lógica de Organización
    organizacion = models.ForeignKey(
        Organizacion, 
        on_delete=models.CASCADE, 
        related_name='usuarios',
        null=True, 
        blank=True
    )
    is_organizacion_admin = models.BooleanField(
        default=False, 
        help_text="Si es True, es el usuario Root que creó la organización."
    )

    # Campos de estado requeridos por Django
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False) # Solo para acceso al admin si fuera necesario
    date_joined = models.DateTimeField(default=timezone.now)

    # ── 2FA (TOTP – compatible con Authy/Google Authenticator) ───────────────
    totp_secret  = models.CharField(max_length=64, blank=True, null=True)
    totp_enabled = models.BooleanField(default=False)

    objects = UserManager()


    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    def __str__(self):
        return f"{self.email} ({self.organizacion.nombre if self.organizacion else 'Sin Org'})"


# ─────────────────────────────────────────────────────────────────────────────
# Códigos de Recuperación (Backup Codes) para 2FA
# ─────────────────────────────────────────────────────────────────────────────
def _generar_codigo():
    """Genera un código aleatorio seguro en formato XXXX-XXXX."""
    alphabet = string.ascii_uppercase + string.digits
    parte1 = ''.join(secrets.choice(alphabet) for _ in range(4))
    parte2 = ''.join(secrets.choice(alphabet) for _ in range(4))
    return f"{parte1}-{parte2}"


class BackupCode(models.Model):
    """
    Código de recuperación de un solo uso.
    Se generan 10 al activar 2FA y uno se consume por cada login de emergencia.
    """
    user      = models.ForeignKey('User', on_delete=models.CASCADE, related_name='backup_codes')
    code      = models.CharField(max_length=9)   # formato XXXX-XXXX
    used      = models.BooleanField(default=False)
    used_at   = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Código de recuperación'
        verbose_name_plural = 'Códigos de recuperación'

    def __str__(self):
        return f"{self.user.email} | {self.code} | {'Usado' if self.used else 'Disponible'}"


def generate_backup_codes(user, cantidad=10):
    """
    Elimina todos los códigos anteriores del usuario y genera `cantidad` códigos nuevos.
    Retorna el queryset de los códigos creados.
    """
    BackupCode.objects.filter(user=user).delete()
    codes = [BackupCode(user=user, code=_generar_codigo()) for _ in range(cantidad)]
    BackupCode.objects.bulk_create(codes)
    return BackupCode.objects.filter(user=user)
