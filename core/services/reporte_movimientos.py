from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDay
from cartera.models import Movimientos_Cartera
from sucursales.models import Sucursales
from proveedores.models import Proveedores

from cartera.services.movimientos import servicio_obtener_monto_restante_por_pagar_factura

def obtener_reporte_movimientos(filtros, user):
    """
    Genera los datos para el reporte de movimientos de cartera.
    """
    if not user or not user.organizacion:
        return {}

    fecha_inicio = filtros.get('fecha_inicio')
    fecha_fin = filtros.get('fecha_fin')
    origen = filtros.get('origen')
    sucursal_id = filtros.get('sucursal')
    proveedor_id = filtros.get('proveedor')

    # Filter By Organization
    qs = Movimientos_Cartera.objects.filter(
        organizacion=user.organizacion
    ).select_related('factura', 'factura__proveedor', 'venta', 'venta__sucursal')

    if fecha_inicio:
        qs = qs.filter(fecha__gte=fecha_inicio)
    
    if fecha_fin:
        qs = qs.filter(fecha__lte=fecha_fin)

    if origen:
        qs = qs.filter(origen=origen)

    if sucursal_id:
        qs = qs.filter(venta__sucursal_id=sucursal_id)

    if proveedor_id:
        qs = qs.filter(factura__proveedor_id=proveedor_id)

    # 1. KPIs Globales
    total_ingresos = qs.filter(origen='INGRESO').aggregate(t=Sum('monto'))['t'] or 0
    total_pagos = qs.filter(origen='PAGO').aggregate(t=Sum('monto'))['t'] or 0
    total_ajustes_suma = qs.filter(origen='AJUSTE_SUMA').aggregate(t=Sum('monto'))['t'] or 0
    total_ajustes_resta = qs.filter(origen='AJUSTE_RESTA').aggregate(t=Sum('monto'))['t'] or 0
    total_cargos = qs.filter(origen='CARGO').aggregate(t=Sum('monto'))['t'] or 0
    
    balance_neto = (total_ingresos + total_ajustes_suma) - (total_pagos + total_ajustes_resta)

    # 2. Datos para Gráficas
    
    # A. Ingresos por Sucursal
    ingresos_sucursal = (qs.filter(origen='INGRESO')
                         .order_by()
                         .values('venta__sucursal__nombre')
                         .annotate(total=Sum('monto'))
                         .order_by('-total'))
    
    chart_sucursal_labels = [item['venta__sucursal__nombre'] or 'Sin Sucursal' for item in ingresos_sucursal]
    chart_sucursal_data = [float(item['total']) for item in ingresos_sucursal]

    # B. Pagos por Proveedor (Top 10)
    pagos_proveedor = (qs.filter(origen='PAGO')
                       .order_by()
                       .values('factura__proveedor__nombre')
                       .annotate(total=Sum('monto'))
                       .order_by('-total')[:10])

    chart_proveedor_labels = [item['factura__proveedor__nombre'] or 'Sin Proveedor' for item in pagos_proveedor]
    chart_proveedor_data = [float(item['total']) for item in pagos_proveedor]
    
    # C. Cargos por Proveedor (Top 10)
    cargos_proveedor = (qs.filter(origen='CARGO')
                       .order_by()
                       .values('factura__proveedor__nombre')
                       .annotate(total=Sum('monto'))
                       .order_by('-total')[:10])

    chart_cargos_labels = [item['factura__proveedor__nombre'] or 'Sin Proveedor' for item in cargos_proveedor]
    chart_cargos_data = [float(item['total']) for item in cargos_proveedor]

    # D. Evolución Diaria (Ingresos vs Pagos - Incluye Ajustes)
    evolucion = (qs.annotate(dia=TruncDay('fecha'))
                 .order_by()
                 .values('dia')
                 .annotate(
                     ingresos=Sum('monto', filter=Q(origen='INGRESO') | Q(origen='AJUSTE_SUMA')),
                     pagos=Sum('monto', filter=Q(origen='PAGO') | Q(origen='AJUSTE_RESTA'))
                 )
                 .order_by('dia'))
    
    chart_timeline_labels = [item['dia'].strftime('%Y-%m-%d') for item in evolucion]
    chart_timeline_ingresos = [float(item['ingresos'] or 0) for item in evolucion]
    chart_timeline_pagos = [float(item['pagos'] or 0) for item in evolucion]

    # 3. Lista Detallada
    detalles_qs = qs.order_by('fecha', 'id')
    detalles = []
    
    for mov in detalles_qs:
        monto_restante = None
        if mov.factura:
            monto_restante = servicio_obtener_monto_restante_por_pagar_factura(mov.factura)
        
        mov.monto_restante_factura = monto_restante
        detalles.append(mov)

    return {
        'total_ingresos': total_ingresos,
        'total_pagos': total_pagos,
        'total_cargos': total_cargos,
        'balance_neto': balance_neto,
        'chart_sucursal_labels': chart_sucursal_labels,
        'chart_sucursal_data': chart_sucursal_data,
        'chart_proveedor_labels': chart_proveedor_labels,
        'chart_proveedor_data': chart_proveedor_data,
        'chart_cargos_labels': chart_cargos_labels,
        'chart_cargos_data': chart_cargos_data,
        'chart_timeline_labels': chart_timeline_labels,
        'chart_timeline_ingresos': chart_timeline_ingresos,
        'chart_timeline_pagos': chart_timeline_pagos,
        'detalles': detalles,
        # Contexto de filtros filtrado por ORG
        'sucursales_list': Sucursales.objects.filter(organizacion=user.organizacion),
        'proveedores_list': Proveedores.objects.filter(organizacion=user.organizacion),
        'origenes_list': Movimientos_Cartera.ORIGENES
    }
