# views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import SucursalForm, VentaForm
from .models import Sucursales, Ventas
from .services.sucursales import (
    servicio_listar_sucursales,
    servicio_crear_sucursal,
    servicio_editar_sucursal,
    servicio_eliminar_sucursal,
)
from .services.ventas import (
    servicio_listar_ventas,
    servicio_crear_venta,
    servicio_editar_venta,
    servicio_eliminar_venta,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolver_next(request, fallback_url):
    """
    Lee ?next= (GET) o next_url (POST).
    Solo acepta rutas relativas para evitar open redirects.
    """
    raw = (
        request.POST.get('next_url')
        or request.GET.get('next')
        or ''
    ).strip()
    if raw and raw.startswith('/'):
        return raw
    return fallback_url


# ---------------------------------------------------------------------------
# SUCURSALES
# ---------------------------------------------------------------------------

@login_required
def lista_sucursales(request):
    sucursales = servicio_listar_sucursales(user=request.user)
    return render(request, 'sucursales/sucursales.html', {
        'sucursales': sucursales
    })


@login_required
def crear_sucursal(request):
    if request.method == 'POST':
        form = SucursalForm(request.POST)
        if form.is_valid():
            try:
                servicio_crear_sucursal(form.cleaned_data, user=request.user)
                messages.success(request, 'Sucursal creada correctamente.')
                return redirect('lista-sucursales')
            except ValidationError as e:
                form.add_error(None, e.message)
    else:
        form = SucursalForm()

    return render(request, 'sucursales/crear_sucursal.html', {
        'form': form,
        'titulo': 'Crear sucursal'
    })


@login_required
def editar_sucursal(request, sucursal_id):
    sucursal = get_object_or_404(Sucursales, pk=sucursal_id, organizacion=request.user.organizacion)

    if request.method == 'POST':
        form = SucursalForm(request.POST, instance=sucursal)
        if form.is_valid():
            try:
                servicio_editar_sucursal(sucursal, form.cleaned_data, user=request.user)
                messages.success(request, 'Sucursal actualizada correctamente.')
                return redirect('lista-sucursales')
            except ValidationError as e:
                form.add_error(None, e.message)
    else:
        form = SucursalForm(instance=sucursal)

    return render(request, 'sucursales/editar_sucursal.html', {
        'form': form,
        'titulo': 'Editar sucursal'
    })


@login_required
def eliminar_sucursal(request, sucursal_id):
    sucursal = get_object_or_404(Sucursales, pk=sucursal_id, organizacion=request.user.organizacion)

    if request.method == 'POST':
        try:
            servicio_eliminar_sucursal(sucursal, user=request.user)
            messages.success(request, 'Sucursal eliminada correctamente.')
        except ValidationError as e:
            messages.error(request, e.message)

    return redirect('lista-sucursales')


# ---------------------------------------------------------------------------
# VENTAS / INGRESOS
# ---------------------------------------------------------------------------

@login_required
def lista_ventas(request):
    """
    Lista de ventas con filtros por sucursal y rango de fechas.
    """
    sucursales = Sucursales.objects.filter(organizacion=request.user.organizacion)

    filters = {
        'sucursal':    request.GET.get('sucursal'),
        'fecha_desde': request.GET.get('fecha_desde'),
        'fecha_hasta': request.GET.get('fecha_hasta'),
    }
    filters_clean = {k: v for k, v in filters.items() if v}

    ventas = servicio_listar_ventas(filters=filters_clean, user=request.user)

    # Total filtrado
    from decimal import Decimal
    total = sum(v.monto for v in ventas) if ventas else Decimal('0')

    from datetime import datetime
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    lista_url  = reverse('lista-ventas')

    return render(request, 'ventas/lista_ventas.html', {
        'ventas':     ventas,
        'sucursales': sucursales,
        'filters':    filters,
        'total':      total,
        'fecha_hoy':  fecha_hoy,
        'lista_url':  lista_url,
    })


@login_required
def crear_venta(request, fecha_str):
    fallback = reverse('detalle-dia', args=[fecha_str])
    next_url  = request.GET.get('next', fallback)

    if request.method == 'POST':
        form = VentaForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                servicio_crear_venta(form.cleaned_data, user=request.user)
                messages.success(request, 'Ingreso registrado correctamente.')
                dest = _resolver_next(request, fallback)
                return redirect(dest)
            except ValidationError as e:
                form.add_error(None, e.message)
    else:
        form = VentaForm(initial={'fecha': fecha_str}, user=request.user)

    return render(request, 'ventas/crear_venta.html', {
        'form':    form,
        'titulo':  'Registrar Ingreso',
        'fecha':   fecha_str,
        'next_url': next_url,
    })


@login_required
def editar_venta(request, venta_id, fecha_str):
    venta    = get_object_or_404(Ventas, pk=venta_id, sucursal__organizacion=request.user.organizacion)
    fallback = reverse('detalle-dia', args=[fecha_str])
    next_url  = request.GET.get('next', fallback)

    if request.method == 'POST':
        form = VentaForm(request.POST, instance=venta, user=request.user)
        if form.is_valid():
            try:
                servicio_editar_venta(venta, form.cleaned_data, user=request.user)
                messages.success(request, 'Ingreso actualizado correctamente.')
                dest = _resolver_next(request, fallback)
                return redirect(dest)
            except ValidationError as e:
                form.add_error(None, e.message)
    else:
        form = VentaForm(instance=venta, user=request.user)

    return render(request, 'ventas/editar_venta.html', {
        'form':    form,
        'titulo':  'Editar Ingreso',
        'fecha':   fecha_str,
        'venta':   venta,
        'next_url': next_url,
    })


@login_required
def eliminar_venta(request, venta_id, fecha_str):
    venta    = get_object_or_404(Ventas, pk=venta_id, sucursal__organizacion=request.user.organizacion)
    fallback = reverse('detalle-dia', args=[fecha_str])

    if request.method == 'POST':
        next_url = _resolver_next(request, fallback)
        try:
            servicio_eliminar_venta(venta, user=request.user)
            messages.success(request, 'Ingreso eliminado correctamente.')
        except ValidationError as e:
            messages.error(request, e.message)
        return redirect(next_url)

    return redirect(fallback)
