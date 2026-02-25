from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DeleteView
from django.contrib import messages
from .models import Proveedores
from .forms import ProveedorForm, CuentaMaestraForm
from django.core.exceptions import ValidationError
from .services.proveedor import *
from .services.cuenta_maestra import *
@login_required
def lista_proveedores(request):
    filters = {
        'nombre': request.GET.get('nombre'),
        'telefono': request.GET.get('telefono'),
        'email': request.GET.get('email'),
    }
    # Filtramos por usuario (org)
    proveedores = servicio_obtener_proveedores(filters, user=request.user)
    
    return render(
        request,
        'proveedores/proveedores.html',
        {
            'proveedores': proveedores,
            'filters': filters
        }
    )


@login_required
def crear_proveedor(request):
    if request.method == 'POST':
        form = ProveedorForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                # Pasamos request.user para asignar la organización
                servicio_crear_proveedor(form.cleaned_data, user=request.user)
                messages.success(request, 'Proveedor creado exitosamente.')
                return redirect('lista-proveedores')
            except ValidationError as e:
                form.add_error(None, e.message)
    else:
        form = ProveedorForm(user=request.user)

    return render(request, 'proveedores/crear_proveedor.html', {'form': form})


@login_required
def editar_proveedor(request, pk):
    # Aseguramos que el proveedor pertenezca a la organización del usuario
    proveedor = get_object_or_404(Proveedores, pk=pk, organizacion=request.user.organizacion)

    if request.method == 'POST':
        form = ProveedorForm(request.POST, instance=proveedor, user=request.user)

        if form.is_valid():
            try:
                servicio_editar_proveedor(
                    proveedor=proveedor,
                    data=form.cleaned_data,
                    user=request.user
                )
                messages.success(
                    request,
                    'Proveedor actualizado exitosamente.'
                )
                return redirect('lista-proveedores')

            except ValidationError as e:
                form.add_error(None, e.message)

    else:
        form = ProveedorForm(instance=proveedor, user=request.user)

    return render(
        request,
        'proveedores/editar_proveedor.html',
        {
            'form': form,
            'proveedor': proveedor
        }
    )


@login_required
def eliminarProveedor(request, pk):
    # Aseguramos que el proveedor pertenezca a la organización del usuario
    proveedor = get_object_or_404(Proveedores, pk=pk, organizacion=request.user.organizacion)

    if request.method == 'POST':
        try:
            servicio_eliminar_proveedor(proveedor=proveedor, user=request.user)
            messages.success(
                request,
                'Proveedor eliminado correctamente.'
            )
        except ValidationError as e:
            messages.error(request, e.message)

        return redirect('lista-proveedores')


# -----------------------------------------------------------------------------
# VISTAS DE CUENTA MAESTRA
# -----------------------------------------------------------------------------

@login_required
def ver_cuenta_maestra(request):
    # Pasamos el usuario para filtrar por organización
    cuenta = servicio_obtener_cuenta_maestra(user=request.user)
    
    if not cuenta:
        # Si no existe, redirigir a crear
        messages.info(request, 'No existe una Cuenta Maestra registrada. Por favor cree una.')
        return redirect('crear-cuenta-maestra')

    return render(request, 'proveedores/cuenta_maestra/cuenta_maestra.html', {'cuenta': cuenta})


@login_required
def crear_cuenta_maestra(request):
    cuenta_existente = servicio_obtener_cuenta_maestra(user=request.user)
    if cuenta_existente:
        messages.warning(request, 'Ya existe una Cuenta Maestra. Solo se permite una registro.')
        return redirect('ver-cuenta-maestra')

    if request.method == 'POST':
        form = CuentaMaestraForm(request.POST)
        if form.is_valid():
            try:
                servicio_crear_cuenta_maestra(form.cleaned_data, user=request.user)
                messages.success(request, 'Cuenta Maestra creada exitosamente.')
                return redirect('ver-cuenta-maestra')
            except ValidationError as e:
                form.add_error(None, e.message)
    else:
        form = CuentaMaestraForm()

    return render(request, 'proveedores/cuenta_maestra/crear_cuenta_maestra.html', {'form': form})


@login_required
def editar_cuenta_maestra(request):
    cuenta = servicio_obtener_cuenta_maestra(user=request.user)
    if not cuenta:
        messages.error(request, 'No se encontró la Cuenta Maestra para editar.')
        return redirect('crear-cuenta-maestra')

    if request.method == 'POST':
        form = CuentaMaestraForm(request.POST, instance=cuenta)
        if form.is_valid():
            try:
                servicio_editar_cuenta_maestra(cuenta, form.cleaned_data, user=request.user)
                messages.success(request, 'Cuenta Maestra actualizada exitosamente.')
                return redirect('ver-cuenta-maestra')
            except ValidationError as e:
                form.add_error(None, e.message)
    else:
        form = CuentaMaestraForm(instance=cuenta)

    return render(request, 'proveedores/cuenta_maestra/editar_cuenta_maestra.html', {'form': form, 'cuenta': cuenta})
