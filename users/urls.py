from django.urls import path
from .views import (
    login_view, index, logout_view,
    users_list, delete_user, create_user,
    register_organization, editar_organizacion,
    change_password, verificar_2fa_login,
)

urlpatterns = [
    path('', login_view, name='login'),
    path('index/', index, name='index'),
    path('logout/', logout_view, name='logout'),
    path('login/', login_view, name='login'),
    path('users/list/', users_list, name='users-list'),
    path('user/delete/<int:user_id>/', delete_user, name='user-delete'),
    path('user/create/', create_user, name='user-create'),
    path('register/', register_organization, name='register-organization'),
    path('organizacion/editar/', editar_organizacion, name='editar-organizacion'),
    # 2FA login step 2
    path('2fa/verificar/', verificar_2fa_login, name='verificar-2fa-login'),
]
