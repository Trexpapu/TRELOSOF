from django.urls import path
from . import views

urlpatterns = [
    path('', views.configuracion_index, name='configuracion-index'),
    path('contrasena/', views.cambiar_contrasena, name='change-password'),
    # 2FA – Setup
    path('2fa/setup/', views.setup_2fa, name='setup-2fa'),
    path('2fa/confirmar/', views.confirmar_2fa, name='confirmar-2fa'),
    path('2fa/desactivar/', views.desactivar_2fa, name='desactivar-2fa'),
    # 2FA – Backup codes
    path('2fa/codigos/', views.ver_codigos_recuperacion, name='codigos-recuperacion'),
    path('2fa/codigos/regenerar/', views.regenerar_codigos, name='regenerar-codigos'),
]
