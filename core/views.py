from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from datetime import datetime, timedelta
from django.utils import timezone
from sucursales.models import Sucursales

# Import Swapped Services
from .services.calendario import obtener_datos_calendario
from .services.detalle_dia import obtener_datos_detalle_dia, tabulacion_pdf, tabulacion_simple_pdf
from .services.reporte_ventas import (
    reporte_ventas_por_sucursal, 
    reporte_ventas_diarias,
    obtener_alertas_criticas
)
from .services.reporte_factura import obtener_reporte_facturas
from .services.reporte_movimientos import obtener_reporte_movimientos
import json
from django.http import HttpResponse, JsonResponse

@login_required
def calendario_financiero(request):
    year = request.GET.get('year')
    month = request.GET.get('month')
    folio_busqueda = request.GET.get('folio', '').strip()
    
    # Pasamos request.user al servicio
    context = obtener_datos_calendario(year, month, request.user, folio_busqueda)
    
    return render(request, 'core/calendario.html', context)


@login_required
def detalle_dia(request, fecha_str):
    context = obtener_datos_detalle_dia(fecha_str, request.user)
    return render(request, 'core/detalle_dia.html', context)




@login_required
def ventas_por_sucursal(request):
    # 1. Valores por defecto
    hoy = timezone.now().date()
    fecha_inicio = hoy.replace(day=1) 
    fecha_fin = hoy
    sucursal_id = None
    monto_critico = 0
    
    # 2. Si es POST, sobreescribimos con los filtros
    if request.method == 'POST':
        try:
            fecha_inicio = datetime.strptime(request.POST.get('fecha_inicio'), '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(request.POST.get('fecha_fin'), '%Y-%m-%d').date()
            sucursal_id = request.POST.get('sucursal') or None
            monto_critico = request.POST.get('monto_critico') or 0
        except (ValueError, TypeError):
            pass 

    # 3. Obtener datos (Pasando user)
    reporte = reporte_ventas_por_sucursal(fecha_inicio, fecha_fin, request.user, sucursal_id)
    reporte_diario = reporte_ventas_diarias(fecha_inicio, fecha_fin, request.user, sucursal_id)
    
    # Obtener alertas si hay un monto crítico definido
    alertas = obtener_alertas_criticas(fecha_inicio, fecha_fin, request.user, sucursal_id, monto_critico)
    
    total_general = sum(item['total_ventas'] for item in reporte)

    # 4. Preparar datos para gráficas
    chart_labels = [item['sucursal__nombre'] for item in reporte]
    chart_data = [float(item['total_ventas']) for item in reporte]

    daily_labels = [item['dia'].strftime('%d/%m') for item in reporte_diario]
    daily_data = [float(item['total']) for item in reporte_diario]

    # Calcular porcentajes para la tabla
    for item in reporte:
        item['porcentaje'] = (item['total_ventas'] / total_general * 100) if total_general > 0 else 0

    # Filtramos la lista de sucursales en el contexto también
    sucursales_list = Sucursales.objects.none()
    if request.user.organizacion:
        sucursales_list = Sucursales.objects.filter(organizacion=request.user.organizacion)

    context = {
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'sucursal_id': int(sucursal_id) if sucursal_id else None,
        'monto_critico': monto_critico,
        'sucursales': sucursales_list,
        'reporte': reporte,
        'total_general': total_general,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'daily_labels': daily_labels,
        'daily_data': daily_data,
        'alertas': alertas, 
    }

    return render(request, 'core/reportes/ventas/reporte_ventas_sucursal.html', context)


@login_required
def reporte_facturas(request):
    # Valores por defecto: Mes actual
    hoy = timezone.now().date()
    fecha_inicio = hoy.replace(day=1)
    fecha_fin = hoy
    proveedor_id = None
    estado = None

    if request.method == 'POST':
        try:
            fecha_inicio = datetime.strptime(request.POST.get('fecha_inicio'), '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(request.POST.get('fecha_fin'), '%Y-%m-%d').date()
            proveedor_id = request.POST.get('proveedor') or None
            estado = request.POST.get('estado') or None
        except (ValueError, TypeError):
            pass

    filtros = {
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'proveedor': proveedor_id,
        'estado': estado
    }

    # Pasamos user
    context = obtener_reporte_facturas(filtros, request.user)
    
    # Agregar filtros al contexto para mantener el estado del formulario
    context.update({
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'proveedor_id': int(proveedor_id) if proveedor_id else None,
        'estado_actual': estado
    })

    return render(request, 'core/reportes/facturas/reporte_facturas.html', context)


@login_required
def reporte_movimientos(request):
    hoy = timezone.now().date()
    fecha_inicio = hoy.replace(day=1)
    # Default: Todo el mes actual (incluyendo futuro cercano)
    ultimo_dia_mes = (hoy.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    fecha_fin = ultimo_dia_mes

    origen = None
    sucursal_id = None
    proveedor_id = None

    if request.method == 'POST':
        try:
            val_inicio = request.POST.get('fecha_inicio')
            val_fin = request.POST.get('fecha_fin')
            if val_inicio:
                fecha_inicio = datetime.strptime(val_inicio, '%Y-%m-%d').date()
            if val_fin:
                fecha_fin = datetime.strptime(val_fin, '%Y-%m-%d').date()
            
            origen = request.POST.get('origen') or None
            sucursal_id = request.POST.get('sucursal') or None
            proveedor_id = request.POST.get('proveedor') or None
        except (ValueError, TypeError):
            pass

    filtros = {
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'origen': origen,
        'sucursal': sucursal_id,
        'proveedor': proveedor_id
    }
    
    # Pasamos user
    context = obtener_reporte_movimientos(filtros, request.user)
    
    # Mantener filtros en el contexto
    context.update({
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'origen_actual': origen,
        'sucursal_actual': int(sucursal_id) if sucursal_id else None,
        'proveedor_actual': int(proveedor_id) if proveedor_id else None
    })

    return render(request, 'core/reportes/movimientos/reporte_movimientos.html', context)

@login_required
def exportar_tabulacion(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            # Pasamos user
            pdf_buffer = tabulacion_pdf(data, request.user)
            
            response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="Corte_Caja_{data.get("fecha")}.pdf"'
            return response
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def herramienta_tabulador(request):
    hoy = timezone.now().date()
    return render(request, 'core/tabulador.html', {'hoy': hoy})

@login_required
def exportar_tabulacion_simple(request):
    """
    Vista específica para exportar el PDF desde la herramienta de tabulador (sin comparativas).
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            # tabulacion_simple_pdf no necesita user porque no accede a BD, solo imprime lo que recibe en data
            pdf_buffer = tabulacion_simple_pdf(data)
            
            response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="Tabulacion_{data.get("fecha")}.pdf"'
            return response
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Method not allowed'}, status=405)