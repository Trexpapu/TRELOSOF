from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from .forms import *
from .services.movimientos import *
from facturas.models import Facturas
from datetime import date, datetime
from sucursales.models import Sucursales
from decimal import Decimal, InvalidOperation
from .services.movimiento_ajustes import crear_ajuste

@login_required
def pagar_factura(request, factura_id, fecha_str):
    factura = get_object_or_404(Facturas, pk=factura_id, organizacion=request.user.organizacion)
    
    monto_restante = servicio_obtener_monto_restante_por_pagar_factura(factura)
    fecha_seleccionada = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    
    if request.method == 'POST':
        form = PagoForm(request.POST, factura=factura)
        if form.is_valid():
            try:
                registrar_movimiento_pago_factura({
                    'factura': factura,
                    'monto': form.cleaned_data['monto'],
                    'fecha': fecha_seleccionada
                }, user=request.user)
                return redirect('detalle-dia', fecha_seleccionada)
            except ValidationError as e:
                form.add_error(None, e.message)
    else:
        form = PagoForm(factura=factura)

    return render(request, 'movimientos/pagar_factura.html', {
        'form': form,
        'factura' : factura,
        'monto_restante': monto_restante,
        'fecha_str' : fecha_seleccionada
    })


@login_required
def editar_pago_factura(request, movimiento_id):
    movimiento = get_object_or_404(Movimientos_Cartera, pk=movimiento_id, organizacion=request.user.organizacion)
    
    if request.method == 'POST':
        form = PagoForm(request.POST, factura=movimiento.factura)
        if form.is_valid():
            try:
                servicio_editar_movimiento_pago_factura(movimiento, form.cleaned_data, user=request.user)
                return redirect('lista-movimientos')
            except ValidationError as e:
                form.add_error(None, e.message)
            
    else:
        form = PagoForm(factura=movimiento.factura)

    return render(request, 'movimientos/editar_movimiento.html', {
        'form': form,
        'movimiento': movimiento,
    })

@login_required
def eliminar_pago_factura(request, movimiento_id):
    movimiento = get_object_or_404(Movimientos_Cartera, pk=movimiento_id, organizacion=request.user.organizacion)
    if request.method == 'POST':
        try:
            servicio_eliminar_movimiento_pago_factura(movimiento, user=request.user)
            messages.success(request, 'Movimiento eliminado correctamente.')
            return redirect('lista-movimientos')
        except ValidationError as e:
            messages.error(request, e.message)
            
    return redirect('lista-movimientos')
    
@login_required
def lista_movimientos(request):
    # Recopilar filtros del request
    filters = {
        'fecha_inicio': request.GET.get('fecha_inicio'),
        'fecha_fin': request.GET.get('fecha_fin'),
        'origen': request.GET.get('origen'),
        'sucursal': request.GET.get('sucursal'),
        'folio': request.GET.get('folio')
    }
    
    # Limpiar filtros vacíos
    filters = {k: v for k, v in filters.items() if v}
    
    movimientos = servicio_obtener_movimientos(filters, user=request.user)
    
    # Obtener sucursales para el select del filtro (FILTRADO POR ORG)
    if request.user.organizacion:
        sucursales = Sucursales.objects.filter(organizacion=request.user.organizacion)
    else:
        sucursales = Sucursales.objects.none()
    
    # Opciones de origen
    origenes = Movimientos_Cartera.ORIGENES
    
    context = {
        'movimientos': movimientos,
        'sucursales': sucursales,
        'origenes': origenes,
        'filters': filters
    }
    return render(request, 'movimientos/movimientos.html', context)

@login_required
def pagar_facturas_masivas(request):
    if request.method == 'POST':
        ids_str = request.POST.get('fechas_ids', '')
        fecha_pago_str = request.POST.get('fecha_pago', '')
        if not ids_str:
            messages.warning(request, "No se enviaron facturas para pagar.")
            return redirect(request.META.get('HTTP_REFERER', '/'))

        try:
            ids_list = [int(x) for x in ids_str.split(',') if x.isdigit()]
            
            # Convertir string fecha a objeto date si existe, sino None (el servicio usará hoy)
            fecha_pago = None
            if fecha_pago_str:
                try:
                    fecha_pago = datetime.strptime(fecha_pago_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            # Pasamos user para validar organización de las facturas
            reporte = servicio_pagar_facturas_masivas(ids_list, fecha_pago, user=request.user)
            
            # Mensajes de reporte
            if reporte['pagadas'] > 0:
                messages.success(request, f"Se pagaron {reporte['pagadas']} facturas por ${reporte['monto_total']:,.2f}.")
            
            if reporte['omitidas'] > 0:
                messages.size_check = False # Hacky flag? No, just straightforward msg
                messages.warning(request, f"Se omitieron {reporte['omitidas']} facturas (ya pagadas o sin saldo o de otra org).")
                
            if reporte['errores'] > 0:
                messages.error(request, f"Ocurrieron {reporte['errores']} errores. Revisa los detalles.")
                for detalle in reporte['detalles']:
                    messages.error(request, detalle)

        except Exception as e:
            messages.error(request, f"Error al procesar pagos masivos: {str(e)}")
            
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def crear_ajuste_saldo(request):
    if request.method == 'POST':
        tipo = request.POST.get('tipo')
        monto = request.POST.get('monto')
        descripcion = request.POST.get('descripcion')
        fecha_str = request.POST.get('fecha')
        
        try:
            val_monto = Decimal(monto)
            if val_monto <= 0:
                messages.error(request, 'El monto debe ser mayor a 0.')
                return redirect(request.META.get('HTTP_REFERER', '/'))
            
            # Parse date if provided
            fecha_ajuste = None
            if fecha_str:
                try:
                    fecha_ajuste = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
                
            crear_ajuste(val_monto, tipo, descripcion, fecha=fecha_ajuste, user=request.user)
            messages.success(request, f'Ajuste realizado correctamente: {tipo} ({fecha_str or "Hoy"})')
            
        except (InvalidOperation, ValueError):
            messages.error(request, 'Monto inválido.')
        except Exception as e:
            messages.error(request, f'Error desconocido: {str(e)}')
            
    return redirect(request.META.get('HTTP_REFERER', '/'))
