from django.db import transaction
from ..models import User, Organizacion
from django.core.exceptions import ValidationError

@transaction.atomic
def register_organizacion_service(data):
    """
    Crea una organizacion y su usuario administrador (root).
    """
    nombre_org = data.get('nombre_organizacion')
    email = data.get('email')
    password = data.get('password1')
    first_name = data.get('first_name')
    last_name = data.get('last_name')

    # 1. Crear Organización
    organizacion = Organizacion.objects.create(
        nombre=nombre_org,
        is_active=True
    )

    # 2. Crear Usuario Admin
    user = User.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        is_organizacion_admin=True,
        organizacion=organizacion
    )
    
    return organizacion, user

def create_user_for_organizacion_service(data, admin_user):
    """
    Crea un usuario normal ligado a la misma organización del admin.
    Límite dinámico dependiente del plan de suscripción actual.
    """
    if not admin_user.organizacion:
        raise ValidationError("El usuario administrador no tiene una organización asignada.")

    if not admin_user.is_organizacion_admin:
        raise ValidationError("Solo el administrador de la organización puede crear usuarios.")

    # ── Verificar límite del plan ─────────────────────────────────────────────
    # Obtener límite desde la suscripción de la organización
    limite_usuarios = 4
    if hasattr(admin_user.organizacion, 'suscripcion'):
        limite_usuarios = admin_user.organizacion.suscripcion.max_usuarios
        
    total_actuales = User.objects.filter(organizacion=admin_user.organizacion).count()
    if total_actuales >= limite_usuarios:
        raise ValidationError(
            f"Límite alcanzado: tu plan actual permite un máximo de {limite_usuarios} usuarios "
            "por organización. Cambia a un plan superior para añadir más colaboradores."
        )

    email = data.get('email')
    password = data.get('password1')
    first_name = data.get('first_name')
    last_name = data.get('last_name')

    user = User.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        organizacion=admin_user.organizacion, # Hereda la organización
        is_organizacion_admin=False # Usuario normal
    )

    return user

def list_organization_users_service(admin_user, search_query=''):
    """
    Retorna la query de usuarios pertenecientes a la misma organización que el admin.
    Excluye al propio admin de la lista si se desea, o lo incluye. 
    Aquí retornamos todos los de la org.
    """
    if not admin_user.organizacion:
        return User.objects.none()

    users = User.objects.filter(organizacion=admin_user.organizacion).order_by('-date_joined')
    
    if search_query:
        users = users.filter(
            email__icontains=search_query
        ) | users.filter(
            first_name__icontains=search_query
        ) | users.filter(
            last_name__icontains=search_query
        )
        
    return users

def delete_organization_user_service(user_id, admin_user):
    """
    Elimina un usuario de la organización, verificando permisos.
    """
    try:
        user_to_delete = User.objects.get(id=user_id)
    except User.DoesNotExist:
        raise ValidationError("Usuario no encontrado.")

    # Validaciones de seguridad
    if user_to_delete.organizacion != admin_user.organizacion:
        raise ValidationError("No tienes permisos para eliminar este usuario.")
    
    if user_to_delete == admin_user:
        raise ValidationError("No puedes eliminarte a ti mismo desde aquí.")

    if user_to_delete.is_organizacion_admin:
         raise ValidationError("No se puede eliminar al administrador principal de la organización.")

    user_to_delete.delete()
