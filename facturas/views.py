from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.urls import reverse
from facturas.models import *
from .forms import FacturaCreateForm, FacturaEditForm
from .services.facturas import *
from datetime import date, datetime
from proveedores.models import Proveedores


def _resolver_next(request, fallback_url):
    """
    Lee ?next= del GET o next_url del POST.
    Solo acepta rutas relativas para evitar redirecciones abiertas.
    Si no viene nada válido, usa fallback_url.
    """
    next_url = (
        request.POST.get('next_url')
        or request.GET.get('next')
        or ''
    ).strip()

    # Seguridad: solo rutas relativas (no saltar a otros dominios)
    if next_url and next_url.startswith('/'):
        return next_url
    return fallback_url


@login_required
def crear_factura(request, fecha_str):
    # URL de retorno: viene de ?next= (lista_facturas) o fallback a detalle-dia
    fallback = reverse('detalle-dia', args=[fecha_str])
    next_url = request.GET.get('next', fallback)

    if request.method == 'POST':
        form = FacturaCreateForm(request.POST, user=request.user)

        if form.is_valid():
            try:
                payload = {
                    "factura": {
                        "proveedor":       form.cleaned_data['proveedor'],
                        "folio":           form.cleaned_data.get('folio'),
                        "tipo":            form.cleaned_data['tipo'],
                        "monto":           form.cleaned_data['monto'],
                        "notas":           form.cleaned_data.get('notas', ''),
                        "cuenta_override": form.cleaned_data.get('cuenta_override', 'PROVEEDOR'),
                    },
                    "pagos": [
                        {"fecha": fecha, "monto": monto}
                        for fecha, monto in zip(
                            form.cleaned_data['fechas_pago'],
                            form.cleaned_data['montos_pago']
                        )
                    ]
                }

                servicio_crear_factura_con_fechas(data=payload, user=request.user)
                messages.success(request, 'Factura creada correctamente.')

                # Redirige al origen: detalle-dia o lista-facturas
                dest = _resolver_next(request, fallback)
                return redirect(dest)

            except ValidationError as e:
                form.add_error(None, e.message)
    else:
        form = FacturaCreateForm(user=request.user)

    return render(request, 'facturas/crear_factura.html', {
        'form':      form,
        'fecha_str': fecha_str,
        'next_url':  next_url,      # pasa al template para el botón Regresar y campo oculto
    })


@login_required
def editar_factura(request, factura_id, fecha_str):
    factura = get_object_or_404(Facturas, pk=factura_id, organizacion=request.user.organizacion)
    fecha_seleccionada = datetime.strptime(fecha_str, '%Y-%m-%d').date()

    fallback = reverse('detalle-dia', args=[fecha_str])
    next_url = request.GET.get('next', fallback)

    if request.method == 'POST':
        form = FacturaEditForm(request.POST, instance=factura, user=request.user)
        if form.is_valid():
            try:
                servicio_editar_factura(factura, form.cleaned_data, user=request.user)
                messages.success(request, 'Factura actualizada correctamente.')

                dest = _resolver_next(request, fallback)
                return redirect(dest)
            except ValidationError as e:
                form.add_error(None, e.message)
    else:
        form = FacturaEditForm(instance=factura, user=request.user)

    schedules = FacturasFechasDePago.objects.filter(factura=factura).order_by('fecha_por_pagar')
    pagos_existentes = [
        {
            'fecha': schedule.fecha_por_pagar.strftime('%Y-%m-%d'),
            'monto': float(schedule.monto_por_pagar)
        }
        for schedule in schedules
    ]

    return render(request, 'facturas/editar_factura.html', {
        'form':               form,
        'factura':            factura,
        'pagos_existentes':   pagos_existentes,
        'fecha_seleccionada': fecha_seleccionada,
        'next_url':           next_url,     # pasa al template
    })


@login_required
def eliminar_factura(request, factura_id, fecha_str):
    factura = get_object_or_404(Facturas, pk=factura_id, organizacion=request.user.organizacion)

    fallback = reverse('detalle-dia', args=[fecha_str])

    if request.method == 'POST':
        next_url = _resolver_next(request, fallback)
        servicio_eliminar_factura(factura, user=request.user)
        messages.success(request, 'Factura eliminada correctamente.')
        return redirect(next_url)

    return redirect(fallback)


@login_required
def lista_facturas(request):
    filters = {
        'folio':     request.GET.get('folio'),
        'proveedor': request.GET.get('proveedor'),
        'estado':    request.GET.get('estado'),
        'tipo':      request.GET.get('tipo'),
    }
    filters = {k: v for k, v in filters.items() if v}

    facturas = servicio_obtener_facturas(filters, user=request.user)

    if request.user.organizacion:
        proveedores = Proveedores.objects.filter(organizacion=request.user.organizacion)
    else:
        proveedores = Proveedores.objects.none()

    estados  = Facturas.ESTADOS
    tipos    = Facturas.TIPOS
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')

    # URL de next para que los botones editar/crear regresen aquí
    lista_url = reverse('lista-facturas')

    return render(request, 'facturas/lista_facturas.html', {
        'facturas':   facturas,
        'proveedores': proveedores,
        'estados':    estados,
        'tipos':      tipos,
        'filters':    filters,
        'fecha_hoy':  fecha_hoy,
        'lista_url':  lista_url,    # se usa en los links del template
    })
