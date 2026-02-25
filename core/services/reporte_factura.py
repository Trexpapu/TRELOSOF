from datetime import date
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth, TruncDay
from facturas.models import FacturasFechasDePago, Facturas
from proveedores.models import Proveedores

def obtener_reporte_facturas(filtros, user):
    """
    Genera los datos para el reporte de facturas usando FacturasFechasDePago 
    para análisis temporal y Facturas para análisis de estado.
    """
    if not user or not user.organizacion:
        return {}

    fecha_inicio = filtros.get('fecha_inicio')
    fecha_fin = filtros.get('fecha_fin')
    proveedor_id = filtros.get('proveedor')
    estado = filtros.get('estado')

    # 1. Querysets Base Filtered by Organization
    qs_fechas = FacturasFechasDePago.objects.filter(
        factura__organizacion=user.organizacion
    ).select_related('factura', 'factura__proveedor')

    qs_facturas = Facturas.objects.filter(
        organizacion=user.organizacion
    ).select_related('proveedor')

    if fecha_inicio:
        qs_fechas = qs_fechas.filter(fecha_por_pagar__gte=fecha_inicio)
    
    if fecha_fin:
        qs_fechas = qs_fechas.filter(fecha_por_pagar__lte=fecha_fin)

    if proveedor_id:
        qs_fechas = qs_fechas.filter(factura__proveedor_id=proveedor_id)
        qs_facturas = qs_facturas.filter(proveedor_id=proveedor_id)

    if estado:
        qs_fechas = qs_fechas.filter(factura__estado=estado)
        qs_facturas = qs_facturas.filter(estado=estado)

    # 2. KPIs y Métricas Globales
    total_deuda = qs_fechas.exclude(factura__estado='PAGADO').aggregate(total=Sum('monto_por_pagar'))['total'] or 0
    total_programado = qs_fechas.aggregate(total=Sum('monto_por_pagar'))['total'] or 0
    
    # 3. Datos para Gráficas
    
    # A. Deuda por Proveedor (Top 5)
    deuda_por_proveedor = (qs_fechas.exclude(factura__estado='PAGADO')
                           .values('factura__proveedor__nombre')
                           .annotate(total=Sum('monto_por_pagar'))
                           .order_by('-total')[:10])
    
    chart_proveedor_labels = [item['factura__proveedor__nombre'] for item in deuda_por_proveedor]
    chart_proveedor_data = [float(item['total']) for item in deuda_por_proveedor]

    # B. Distribución por Estado
    distribucion_estado = (qs_facturas.values('estado')
                           .annotate(cantidad=Count('id'), total=Sum('monto'))
                           .order_by('estado'))
    
    chart_estado_labels = [item['estado'] for item in distribucion_estado]
    chart_estado_data = [item['cantidad'] for item in distribucion_estado]
    chart_estado_montos = [float(item['total']) for item in distribucion_estado]

    # C. Calendario de Pagos (Agrupado por día)
    timeline_pagos = (qs_fechas
                      .annotate(dia=TruncDay('fecha_por_pagar'))
                      .values('dia')
                      .annotate(total=Sum('monto_por_pagar'))
                      .order_by('dia'))
            
    chart_timeline_labels = [item['dia'].strftime('%Y-%m-%d') for item in timeline_pagos]
    chart_timeline_data = [float(item['total']) for item in timeline_pagos]
    
    # 4. Tabla Detallada
    detalles = qs_fechas.order_by('fecha_por_pagar')[:100]

    return {
        'total_deuda': total_deuda,
        'total_programado': total_programado,
        'chart_proveedor_labels': chart_proveedor_labels,
        'chart_proveedor_data': chart_proveedor_data,
        'chart_estado_labels': chart_estado_labels,
        'chart_estado_data': chart_estado_data,
        'chart_estado_montos': chart_estado_montos,
        'chart_timeline_labels': chart_timeline_labels,
        'chart_timeline_data': chart_timeline_data,
        'detalles': detalles,
        # Filtros contextuales
        'proveedores': Proveedores.objects.filter(organizacion=user.organizacion),
        'estados': Facturas.ESTADOS
    }
