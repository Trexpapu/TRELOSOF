from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Sum, Count
from facturas.models import FacturasFechasDePago, Facturas
from sucursales.models import Ventas
from cartera.services.movimientos import servicio_obtener_monto_restante_por_pagar_factura
from cartera.services.saldo_cargo import obtener_pagos_del_dia
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

def tabulacion_pdf(data, user):
    fecha_str = data.get('fecha')
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    style_center = styles['Normal']
    style_center.alignment = TA_CENTER
    
    style_right = styles['Normal']
    style_right.alignment = TA_RIGHT

    header_data = [['Confidencial', f"{fecha_str}"]]
    t_header = Table(header_data, colWidths=[230, 230])
    t_header.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(t_header)
    elements.append(Spacer(1, 10))
    
    cargo_total = 0.0
    tabulacion_total = float(data.get('tabulacion_total', 0))
    
    try:
        if fecha_str:
            fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        else:
            fecha_obj = timezone.now().date()
            
        # Filtro de seguridad por organización
        if user and user.organizacion:
             facturas_pago = FacturasFechasDePago.objects.filter(
                fecha_por_pagar=fecha_obj,
                factura__organizacion=user.organizacion
             ).select_related('factura', 'factura__proveedor', 'factura__proveedor__cuenta_maestra')
        else:
             facturas_pago = FacturasFechasDePago.objects.none()

        fact_data = [['CTA', 'NOMBRE PROV', 'TOTAL']]
        
        total_facturas = 0.0
        
        for fp in facturas_pago:
            tipo = fp.factura.tipo
            
            if tipo == 'MERCADO PAGO':
                continue

            proveedor = fp.factura.proveedor
            proveedor_nombre = proveedor.nombre[:35] if proveedor else 'Proveedor Desconocido'

            # Usar la propiedad del modelo que ya respeta cuenta_override
            cuenta_mostrar, _ = fp.factura.cuenta_a_mostrar

            monto = float(fp.monto_por_pagar)
            total_facturas += monto
            
            estilo_celda = styles['Normal']
            estilo_celda.fontSize = 8
            
            cuenta_mostrar = cuenta_mostrar.replace('\n', ' ').replace('\r', '')

            fact_data.append([
                Paragraph(cuenta_mostrar, estilo_celda),
                Paragraph(proveedor_nombre, estilo_celda),
                f"${monto:,.2f}"
            ])

            
        cargo_total = total_facturas
        
        fact_data.append(['', 'TOTAL', f"${cargo_total:,.2f}"])
        
        t_fact = Table(fact_data, colWidths=[180, 200, 100])
        t_fact.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (1, -1), (1, -1), 'RIGHT'),
            ('FONTNAME', (1, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, -1), (2, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f8f9fa')),
        ]))
        elements.append(t_fact)
        
    except Exception as e:
        elements.append(Paragraph(f"Error cargando facturas: {str(e)}", styles['Normal']))

    elements.append(Spacer(1, 15))
    
    filas = data.get('filas', [])
    
    tab_data = [['DENOMINACION', 'CANTIDAD', 'TOTAL']] 
    
    for row in filas:
        denom = row.get('denom')
        cant = row.get('cantidad')
        tot = row.get('total')
        
        if denom is not None:
             tab_data.append([
                f"{denom}",
                f"{cant}",
                f"${float(tot):,.2f}" if tot is not None else "$0.00"
            ])
    
    tab_data.append(['', '', f"${tabulacion_total:,.2f}"])
    
    t_tab = Table(tab_data, colWidths=[100, 100, 100])
    
    t_tab.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, 0), 0.5, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('GRID', (0, 1), (-1, -2), 0.5, colors.black),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
        ('FONTNAME', (2, -1), (2, -1), 'Helvetica-Bold'),
        ('ALIGN', (2, -1), (2, -1), 'RIGHT'),
    ]))
    
    t_tab.hAlign = 'RIGHT'
    
    elements.append(t_tab)
    elements.append(Spacer(1, 15))
    
    diferencia = tabulacion_total - cargo_total
    
    diff_data = [['DIFERENCIA', f"${diferencia:,.2f}"]]
    t_diff = Table(diff_data, colWidths=[150, 150])
    t_diff.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#e2e8f0')), 
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
    ]))
    t_diff.hAlign = 'LEFT'
    
    elements.append(t_diff)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer


def tabulacion_simple_pdf(data):
    """
    Genera un PDF solo con la tabulación de efectivo, manteniendo estilo de cabecera.
    """
    fecha_str = data.get('fecha')
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    header_data = [['Confidencial', f"{fecha_str}"]]
    t_header = Table(header_data, colWidths=[230, 230])
    t_header.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(t_header)
    elements.append(Spacer(1, 20))
    
    tabulacion_total = float(data.get('tabulacion_total', 0))
    filas = data.get('filas', [])
    
    tab_data = [['DENOMINACION', 'CANTIDAD', 'TOTAL']]
    
    for row in filas:
        denom = row.get('denom')
        cant = row.get('cantidad')
        tot = row.get('total')
        if denom is not None:
             tab_data.append([
                f"{denom}",
                f"{cant}",
                f"${float(tot):,.2f}" if tot is not None else "$0.00"
            ])
    
    tab_data.append(['', '', f"${tabulacion_total:,.2f}"])
    
    t_tab = Table(tab_data, colWidths=[100, 100, 100])
    t_tab.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, 0), 0.5, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('GRID', (0, 1), (-1, -2), 0.5, colors.black),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
        ('FONTNAME', (2, -1), (2, -1), 'Helvetica-Bold'),
        ('ALIGN', (2, -1), (2, -1), 'RIGHT'),
    ]))
    t_tab.hAlign = 'CENTER'
    elements.append(t_tab)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer


def obtener_datos_detalle_dia(fecha_str, user):
    try:
        fecha_seleccionada = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        fecha_seleccionada = timezone.now().date()
    
    hoy = timezone.localtime().date()
    
    fecha_anterior = fecha_seleccionada - timedelta(days=1)
    fecha_siguiente = fecha_seleccionada + timedelta(days=1)
    
    # Base Filters using Organization
    if not user or not user.organizacion:
        return {} # Empty context if no org

    fechas_pago_base = FacturasFechasDePago.objects.filter(
        factura__organizacion=user.organizacion 
    )
    ventas_base = Ventas.objects.filter(
        sucursal__organizacion=user.organizacion
    )
    facturas_base = Facturas.objects.filter(
        organizacion=user.organizacion
    )

    # Obtener FECHAS DE PAGO del día
    fechas_pago_dia = fechas_pago_base.filter(
        fecha_por_pagar=fecha_seleccionada
    ).select_related('factura', 'factura__proveedor')
    
    # Obtener ventas del día
    ventas_dia = ventas_base.filter(
        fecha=fecha_seleccionada
    ).select_related('sucursal')
    
    # Calcular totales basados en FECHAS DE PAGO
    cargo_total_dia = fechas_pago_dia.aggregate(
        total=Sum('monto_por_pagar')
    )['total'] or 0
    
    # Calcular cargo para tabulación (Excluyendo Mercado Pago)
    cargo_total_tabulacion = fechas_pago_dia.exclude(
        factura__tipo='MERCADO PAGO'
    ).aggregate(
        total=Sum('monto_por_pagar')
    )['total'] or 0
    
    venta_total_dia = ventas_dia.aggregate(total=Sum('monto'))['total'] or 0
    
    # Obtener facturas únicas para mostrar información consolidada
    facturas_ids = fechas_pago_dia.values_list('factura_id', flat=True).distinct()
    facturas_consolidadas = facturas_base.filter(id__in=facturas_ids)
    
    # Agrupar ventas por sucursal
    ventas_por_sucursal = ventas_dia.values(
        'sucursal__nombre'
    ).annotate(
        total=Sum('monto'),
        cantidad=Count('id')
    ).order_by('-total')
    
    # Calcular ventas necesarias
    promedio_ventas_diarias = 0
    dias_restantes = 0
    
    if fecha_seleccionada > hoy and cargo_total_dia > 0:
        dias_restantes = (fecha_seleccionada - hoy).days
        if dias_restantes > 0:
            promedio_ventas_diarias = cargo_total_dia / dias_restantes
            
    total_pago_del_dia, cantidad_pagos_del_dia = obtener_pagos_del_dia(fecha_seleccionada, user)
    
    # Calcular sumas de montos restantes y totales originales
    cargo_restante_total_dia = 0
    monto_total_facturas_dia = 0
    
    for fecha_pago in fechas_pago_dia:
        fecha_pago.monto_restante = servicio_obtener_monto_restante_por_pagar_factura(
            fecha_pago.factura
        )
        cargo_restante_total_dia += fecha_pago.monto_restante
        monto_total_facturas_dia += fecha_pago.factura.monto

    return {
        'fecha': fecha_seleccionada,
        'hoy': hoy,
        'fecha_anterior': fecha_anterior,
        'fecha_siguiente': fecha_siguiente,
        'fechas_pago_dia': fechas_pago_dia,
        'facturas': facturas_consolidadas,
        'ventas': ventas_dia,
        'cargo_total_dia': cargo_total_dia, 
        'cargo_total_tabulacion': cargo_total_tabulacion, 
        'cargo_restante_total_dia': cargo_restante_total_dia, 
        'monto_total_facturas_dia': monto_total_facturas_dia,
        'venta_total_dia': venta_total_dia,
        'ventas_por_sucursal': ventas_por_sucursal,
        'es_futuro': fecha_seleccionada > hoy,
        'dias_restantes': dias_restantes,
        'promedio_ventas_diarias': promedio_ventas_diarias,
        'fecha_str': fecha_str, 
        'total_pago_del_dia': total_pago_del_dia,
        'cantidad_pagos_del_dia': cantidad_pagos_del_dia,
    }
