"""
Django settings for config project.
"""

import os
import dj_database_url
from pathlib import Path
from decimal import Decimal
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Carga las variables de entorno desde .env (solo en desarrollo).
# En Railway / producción se definen directamente en el panel.
load_dotenv(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-2avp6^v7b!q8!&c%l9+%3(+mz3czd0gx4r4g@0)$%onw$+8=6z')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True') == 'True'

# --- CONFIGURACIÓN DE HOSTS Y SEGURIDAD ---
# En Railway, pon tu dominio real en la variable ALLOWED_HOSTS (sin https://)
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')

# Configuración vital para evitar el error 403 Prohibido
# Genera la lista de orígenes de confianza usando https://
CSRF_TRUSTED_ORIGINS = [
    'https://' + host.strip() for host in ALLOWED_HOSTS if host.strip() and host != '*'
]

# Si DEBUG es False (Producción), forzamos HTTPS
if not DEBUG:
    # Reconoce que Railway usa un proxy para el SSL
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # Redirige todo el tráfico HTTP a HTTPS
    SECURE_SSL_REDIRECT = True
    # Asegura que las cookies solo se envíen por conexiones cifradas
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# --- APLICACIONES ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'widget_tweaks',
    'users',
    'sucursales',
    'facturas',
    'cartera',
    'core',
    'proveedores',
    'suscripciones',
    'configuracion',
    'django.contrib.humanize',
]

# ── Stripe ────────────────────────────────────────────────────────────────────
# Claves leídas desde .env  (o variables de entorno en Railway)
STRIPE_PUBLIC_KEY    = os.getenv('STRIPE_PUBLIC_KEY', '')
STRIPE_SECRET_KEY    = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')

# ── Suscripción ────────────────────────────────────────────────────────────────────
# Ciclo y trial
SUSCRIPCION_TRIAL_DIAS     = int(os.getenv('SUSCRIPCION_TRIAL_DIAS', '0'))
SUSCRIPCION_CICLO_DIAS     = int(os.getenv('SUSCRIPCION_CICLO_DIAS', '30'))

# Plan BÁSICO
PLAN_BASICO_PRECIO        = Decimal(os.getenv('PLAN_BASICO_PRECIO', '199.00'))
PLAN_BASICO_MAX_USUARIOS  = int(os.getenv('PLAN_BASICO_MAX_USUARIOS', '4'))

# Plan PRO
PLAN_PRO_PRECIO           = Decimal(os.getenv('PLAN_PRO_PRECIO', '299.00'))
PLAN_PRO_MAX_USUARIOS     = int(os.getenv('PLAN_PRO_MAX_USUARIOS', '12'))

# Retrocompatibilidad (algunos servicios aún usan SUSCRIPCION_PRECIO_MENSUAL)
SUSCRIPCION_PRECIO_MENSUAL = PLAN_BASICO_PRECIO  # Se sobreescribe al elegir plan


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # Manejo de archivos estáticos
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'suscripciones.middleware.SuscripcionMiddleware',  # 🔒 Bloqueo por suscripción vencida
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# --- BASE DE DATOS ---
# Se conecta a Postgres en Railway automáticamente mediante DATABASE_URL
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600
    )
}

# --- VALIDACIÓN DE CONTRASEÑAS ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- INTERNACIONALIZACIÓN ---
LANGUAGE_CODE = 'es-mx'
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True
USE_L10N = True

# Formatos de fecha y hora
DATETIME_FORMAT = 'd/m/Y H:i'
DATE_FORMAT = 'd/m/Y'
TIME_FORMAT = 'H:i'

# --- ARCHIVOS ESTÁTICOS ---
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Usamos CompressedStaticFilesStorage por ser más robusto si faltan archivos
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --- MODELO DE USUARIO Y LOGIN ---
AUTH_USER_MODEL = "users.User"
LOGIN_URL = 'login'

# Quita el aviso amarillo de los logs sobre llaves primarias
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Logging básico ───────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'loggers': {
        'suscripciones': {'handlers': ['console'], 'level': 'INFO'},
    },
}