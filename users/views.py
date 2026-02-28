from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash

from .forms import UserCreateForm, ChangePasswordForm, OrganizacionRegisterForm, OrganizacionEditForm
from .services.users import (
    register_organizacion_service,
    create_user_for_organizacion_service,
    list_organization_users_service,
    delete_organization_user_service
)
from .services.organizacion import servicio_editar_organizacion
from .models import User
from cartera.services.saldo_cargo import obtener_saldo_global, obtener_cargo_total
from cartera.models import Movimientos_Cartera

# --- VISTAS PUBLICAS (Registro / Login) ---

def register_organization(request):
    """
    Vista pública para registrar una nueva Organización y su Admin.
    Tras el registro exitoso redirige al paso de agregar método de pago.
    """
    if request.user.is_authenticated:
        return redirect('index')

    if request.method == "POST":
        form = OrganizacionRegisterForm(request.POST)
        if form.is_valid():
            try:
                org, user = register_organizacion_service(form.cleaned_data)
                # Login automático tras registro
                login(request, user)
                messages.success(request, f"¡Bienvenido! Organización '{org.nombre}' creada. Tienes 14 días de prueba gratis.")
                # Paso 2: agregar método de pago (puede omitirse)
                return redirect("suscripcion-seleccionar-plan")
            except Exception as e:
                messages.error(request, f"Error al registrar: {e}")
    else:
        form = OrganizacionRegisterForm()

    return render(request, "users/register_organization.html", {"form": form})



def login_view(request):
    if request.user.is_authenticated:
        return redirect('index')

    if request.method == 'POST':
        email    = request.POST.get('email')
        password = request.POST.get('password')

        user = authenticate(request, username=email, password=password)

        if user is not None:
            if user.totp_enabled:
                # Guardar el ID en sesión y redirigir al paso 2FA
                request.session['2fa_user_id']  = user.pk
                request.session['2fa_next_url'] = request.GET.get('next', 'index')
                return redirect('verificar-2fa-login')
            else:
                # Login normal: mostrar recomendación de activar 2FA
                login(request, user)
                messages.info(
                    request,
                    '🔒 Consejo de seguridad: activa la verificación en dos pasos (2FA) '
                    'En Configuración → Seguridad 2FA para proteger tu cuenta.'
                )
                next_url = request.GET.get('next', 'index')
                return redirect(next_url)
        else:
            messages.error(request, 'Email o contraseña incorrectos.')

    return render(request, 'login.html')


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


def verificar_2fa_login(request):
    """
    Segundo paso del login para usuarios con 2FA activado.
    Valida el token TOTP y completa la sesión.
    """
    user_id = request.session.get('2fa_user_id')
    if not user_id:
        return redirect('login')

    from .models import User as UserModel
    try:
        user = UserModel.objects.get(pk=user_id)
    except UserModel.DoesNotExist:
        return redirect('login')

    if request.method == 'POST':
        token = request.POST.get('token', '').strip().upper()
        autenticado = False

        # ── Intentar TOTP primero ──────────────────────────────────────────────
        import pyotp as _pyotp
        totp = _pyotp.TOTP(user.totp_secret)
        if totp.verify(token, valid_window=1):
            autenticado = True
        else:
            # ── Intentar código de recuperación (formato XXXX-XXXX) ───────────
            from users.models import BackupCode
            from django.utils import timezone as _tz
            # Normalizar: si el usuario escribió sin guión (XXXXXXXX) → XXXX-XXXX
            if len(token) == 8 and '-' not in token:
                token = f"{token[:4]}-{token[4:]}"
            try:
                backup = BackupCode.objects.get(user=user, code=token, used=False)
                backup.used    = True
                backup.used_at = _tz.now()
                backup.save(update_fields=['used', 'used_at'])
                autenticado = True
                messages.warning(
                    request,
                    f'⚠️ Accediste con un código de recuperación. '
                    f'Te quedan {BackupCode.objects.filter(user=user, used=False).count()} códigos disponibles.'
                )
            except BackupCode.DoesNotExist:
                pass

        if autenticado:
            login(request, user)
            del request.session['2fa_user_id']
            next_url = request.session.pop('2fa_next_url', 'index')
            return redirect(next_url)
        else:
            messages.error(request, 'Código incorrecto o expirado. Inténtalo de nuevo.')

    return render(request, 'users/verificar_2fa.html', {'email': user.email})


# --- VISTAS PRIVADAS (Gestión de Usuarios de la Organización) ---

@login_required
def users_list(request):
    """
    Lista los usuarios DE LA ORGANIZACIÓN del usuario logueado.
    """
    if not request.user.is_organizacion_admin:
        messages.error(request, "No tienes permisos para ver usuarios.")
        return redirect('index')

    search_query = request.GET.get('search', '')
    users = list_organization_users_service(request.user, search_query)
    
    total_users_count = users.count()
    
    limite_usuarios = 4  # Fallback seguro
    if hasattr(request.user.organizacion, 'suscripcion'):
        limite_usuarios = request.user.organizacion.suscripcion.max_usuarios
        
    context = {
        'users': users,
        'search_query': search_query,
        'total_users': total_users_count,
        'organizacion': request.user.organizacion,
        'limite_usuarios': limite_usuarios,
        'limite_alcanzado': total_users_count >= limite_usuarios,
        'slots_disponibles': max(0, limite_usuarios - total_users_count),
    }
    return render(request, 'users/users_list.html', context)

@login_required
def create_user(request):
    """
    Permite al ADMIN DE LA ORG crear nuevos usuarios (empleados) 
    para SU organización.
    """
    if not request.user.is_organizacion_admin:
        messages.error(request, "No tienes permisos para crear usuarios.")
        return redirect('index')

    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            try:
                create_user_for_organizacion_service(form.cleaned_data, request.user)
                messages.success(request, "Usuario creado correctamente en tu organización.")
                return redirect("users-list")
            except ValidationError as e:
                form.add_error(None, e)
            except Exception as e:
                messages.error(request, f"Error inesperado: {e}")
    else:
        form = UserCreateForm()

    return render(request, "users/create_user.html", {"form": form})

@login_required
def delete_user(request, user_id):
    """
    Elimina un usuario de la organización.
    """
    if not request.user.is_organizacion_admin:
        messages.error(request, "No tienes permisos para eliminar usuarios.")
        return redirect('index')

    if request.method == "POST":
        try:
            delete_organization_user_service(user_id, request.user)
            messages.success(request, "Usuario eliminado correctamente.")
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error al eliminar: {e}")
            
    return redirect("users-list")


@login_required
def change_password(request):
    if request.method == 'POST':
        form = ChangePasswordForm(request.POST)
        if form.is_valid():
            current = form.cleaned_data['current_password']
            new_pass = form.cleaned_data['new_password']
            
            if not request.user.check_password(current):
                form.add_error('current_password', 'Contraseña actual incorrecta')
            else:
                request.user.set_password(new_pass)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Contraseña actualizada.')
                return redirect('index')
    else:
        form = ChangePasswordForm()
    
    return render(request, 'users/change_password.html', {'form': form})

# --- VISTA HOME (INDEX) ---

@login_required
def index(request):
    # Pasamos request.user para filtrar por organización
    saldo_total = obtener_saldo_global(request.user) 
    cargo_total = obtener_cargo_total(request.user)

    # Movimientos filtrados por organización
    queries = Movimientos_Cartera.objects.select_related(
        'factura', 'venta'
    ).order_by('-fecha', '-id')

    if request.user.organizacion:
        queries = queries.filter(organizacion=request.user.organizacion)
    else:
        queries = queries.none()

    movimientos_recientes = queries[:6]

    context = {
        'saldo_total': saldo_total,
        'cargo_total': cargo_total,
        'movimientos_recientes': movimientos_recientes,
    }
    return render(request, 'index.html', context)


# --- VISTAS DE ORGANIZACIÓN ---

@login_required
def editar_organizacion(request):
    """
    Permite al admin de la organización editar el nombre de la misma.
    """
    if not request.user.is_organizacion_admin:
        messages.error(request, "No tienes permisos para editar la organización.")
        return redirect('index')

    organizacion = request.user.organizacion
    if not organizacion:
        messages.error(request, "No tienes una organización asignada.")
        return redirect('index')

    if request.method == 'POST':
        form = OrganizacionEditForm(request.POST, instance=organizacion)
        if form.is_valid():
            try:
                servicio_editar_organizacion(organizacion, form.cleaned_data, user=request.user)
                messages.success(request, 'Organización actualizada correctamente.')
                return redirect('users-list')
            except ValidationError as e:
                form.add_error(None, e.message)
    else:
        form = OrganizacionEditForm(instance=organizacion)

    return render(request, 'organizaciones/editar_organizacion.html', {
        'form': form,
        'organizacion': organizacion
    })