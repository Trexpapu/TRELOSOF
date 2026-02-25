from datetime import date, timedelta
from django.utils import timezone
import calendar
from django.db.models import Sum
from facturas.models import Facturas, FacturasFechasDePago
from sucursales.models import Ventas
from cartera.services.saldo_cargo import obtener_saldo_global as svc_saldo_global, obtener_cargo_total as svc_cargo_total
from cartera.models import Movimientos_Cartera
from django.db.models import Sum, Q

def obtener_datos_calendario(year, month, user, folio_busqueda=''):
    today = timezone.localtime().date()
    
    if year and month:
        try:
            year = int(year)
            month = int(month)
            current_date = date(year, month, 1)
        except (ValueError, TypeError):
            current_date = today
    else:
        current_date = today
        year = current_date.year
        month = current_date.month
    
    # Obtener el primer y último día del mes
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    
    # Obtener datos de Cartera (Globales de la organización)
    saldo_total = svc_saldo_global(user)
    cargo_total = svc_cargo_total(user)

    # Base Querysets filtered by Organization
    fecha_pago_base_qs = FacturasFechasDePago.objects.filter(
        factura__organizacion=user.organizacion
    )
    ventas_base_qs = Ventas.objects.filter(
        sucursal__organizacion=user.organizacion
    )
    movimientos_base_qs = Movimientos_Cartera.objects.filter(
        organizacion=user.organizacion
    )
    facturas_base_qs = Facturas.objects.filter(
        organizacion=user.organizacion
    )

    # Obtener FECHAS DE PAGO del mes (no facturas directamente)
    fechas_pago_mes = fecha_pago_base_qs.filter(
        fecha_por_pagar__range=[first_day, last_day]
    ).select_related('factura', 'factura__proveedor')
    
    # Obtener ventas del mes
    ventas_mes = ventas_base_qs.filter(
        fecha__range=[first_day, last_day]
    )
    
    # Inicializar variables para el filtro de folio
    facturas_filtradas = None
    fechas_factura_filtrada = []
    
    # Procesar búsqueda por folio
    if folio_busqueda:
        # Buscar facturas por folio (búsqueda insensible a mayúsculas y parcial)
        facturas_filtradas = facturas_base_qs.filter(
            folio__icontains=folio_busqueda
        ).prefetch_related('facturasfechasdepago_set')
        
        # Obtener todas las fechas de pago de las facturas encontradas
        for factura in facturas_filtradas:
            # Obtener las fechas de pago de esta factura
            fechas_pago_factura = factura.facturasfechasdepago_set.all()
            for fecha_pago in fechas_pago_factura:
                fechas_factura_filtrada.append({
                    'fecha': fecha_pago.fecha_por_pagar,
                    'factura_id': factura.id,
                    'folio': factura.folio or f"Sin folio (ID: {factura.id})",
                    'proveedor': factura.proveedor.nombre,
                    'monto_por_pagar': fecha_pago.monto_por_pagar
                })
    
    # Calcular totales por día usando fechas de pago
    dias_del_mes = []
    
    # Calcular saldo acumulado previo al mes actual
    # Suma de todas las ventas anteriores al primer día del mes
    ventas_anteriores = ventas_base_qs.filter(fecha__lt=first_day).aggregate(total=Sum('monto'))['total'] or 0
    # Suma de todas las fechas de pago anteriores al primer día del mes
    pagos_anteriores = fecha_pago_base_qs.filter(fecha_por_pagar__lt=first_day).aggregate(total=Sum('monto_por_pagar'))['total'] or 0
    
    # Calcular Ajustes anteriores
    ajustes_anteriores = movimientos_base_qs.filter(fecha__lt=first_day).aggregate(
        suma=Sum('monto', filter=Q(origen='AJUSTE_SUMA')),
        resta=Sum('monto', filter=Q(origen='AJUSTE_RESTA'))
    )
    ajustes_suma_ant = ajustes_anteriores['suma'] or 0
    ajustes_resta_ant = ajustes_anteriores['resta'] or 0
    
    saldo_acumulado = (ventas_anteriores + ajustes_suma_ant) - (pagos_anteriores + ajustes_resta_ant)

    # Crear calendario
    cal = calendar.Calendar(firstweekday=6)  # Empezar en domingo
    
    for semana in cal.monthdatescalendar(year, month):
        semana_dias = []
        for dia_fecha in semana:
            if dia_fecha.month == month:
                # FECHAS DE PAGO del día (no facturas)
                fechas_pago_dia = fechas_pago_mes.filter(fecha_por_pagar=dia_fecha)
                
                # Verificar si este día tiene fechas de pago de la factura buscada
                fechas_filtro_en_dia = []
                if folio_busqueda:
                    for fecha_filtro in fechas_factura_filtrada:
                        if fecha_filtro['fecha'] == dia_fecha:
                            fechas_filtro_en_dia.append(fecha_filtro)
                
                # Sumar montos de las fechas de pago
                total_facturas_dia = fechas_pago_dia.aggregate(
                    total=Sum('monto_por_pagar')
                )['total'] or 0
                
                # Ventas del día
                ventas_dia = ventas_mes.filter(fecha=dia_fecha)
                total_ventas_dia = ventas_dia.aggregate(
                    total=Sum('monto')
                )['total'] or 0
                
                # Calcular Ajustes del día
                ajustes_dia = movimientos_base_qs.filter(fecha=dia_fecha).aggregate(
                    suma=Sum('monto', filter=Q(origen='AJUSTE_SUMA')),
                    resta=Sum('monto', filter=Q(origen='AJUSTE_RESTA'))
                )
                ajuste_suma_dia = ajustes_dia['suma'] or 0
                ajuste_resta_dia = ajustes_dia['resta'] or 0
                
                # Actualizar saldo acumulado (Saldo Inicial del día + Ventas - Pagos + Ajustes)
                saldo_acumulado += (total_ventas_dia - total_facturas_dia + ajuste_suma_dia - ajuste_resta_dia)
                saldo_dia_mostrar = saldo_acumulado

                # Contar facturas PENDIENTES del día
                facturas_pendientes = fechas_pago_dia.filter(
                    factura__estado='PENDIENTE'
                ).count()
                
                # Contar facturas PAGADAS del día
                facturas_pagadas = fechas_pago_dia.filter(
                    factura__estado='PAGADO'
                ).count()
                
                # Contar fechas de pago (no facturas)
                cantidad_fechas_pago = fechas_pago_dia.count()
                
                semana_dias.append({
                    'fecha': dia_fecha,
                    'dia': dia_fecha.day,
                    'es_hoy': dia_fecha == today,
                    'total_facturas': total_facturas_dia,
                    'total_ventas': total_ventas_dia,
                    'saldo_dia': saldo_dia_mostrar,
                    'facturas_pendientes': facturas_pendientes,
                    'facturas_pagadas': facturas_pagadas,
                    'fechas_pago_count': cantidad_fechas_pago,
                    'total_movimientos': total_facturas_dia + total_ventas_dia,
                    'tiene_factura_filtrada': len(fechas_filtro_en_dia) > 0,
                    'fechas_filtro': fechas_filtro_en_dia,
                })
            else:
                semana_dias.append(None)
        dias_del_mes.append(semana_dias)
    
    # Calcular resumen mensual basado en FECHAS DE PAGO
    total_facturas_mes = fechas_pago_mes.aggregate(
        total=Sum('monto_por_pagar')
    )['total'] or 0

    # Total Pagos Realizados en el mes (Movimientos tipo PAGO)
    total_pagos_realizados_mes = movimientos_base_qs.filter(
        origen='PAGO',
        fecha__range=[first_day, last_day]
    ).aggregate(total=Sum('monto'))['total'] or 0

    # Cuota Diaria (Total Cargo Mes / Dias del Mes)
    num_dias_mes = (last_day - first_day).days + 1
    cuota_diaria_necesaria = 0
    if num_dias_mes > 0:
        cuota_diaria_necesaria = total_facturas_mes / num_dias_mes
    
    total_ventas_mes = ventas_mes.aggregate(total=Sum('monto'))['total'] or 0
    
    # Contar fechas de pago pendientes del mes
    fechas_pago_pendientes = fechas_pago_mes.filter(
        factura__estado='PENDIENTE'
    ).count()
    
    # Navegación entre meses
    if month == 1:
        mes_anterior = 12
        anio_anterior = year - 1
    else:
        mes_anterior = month - 1
        anio_anterior = year
    
    if month == 12:
        mes_siguiente = 1
        anio_siguiente = year + 1
    else:
        mes_siguiente = month + 1
        anio_siguiente = year
    
    # Nombres de meses en español
    meses_espanol = [
        'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
        'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
    ]
    
    return {
        'year': year,
        'month': month,
        'month_name': meses_espanol[month - 1],
        'today': today,
        'dias_del_mes': dias_del_mes,
        'saldo_total': saldo_total,
        'cargo_total': cargo_total,
        'total_facturas_mes': total_facturas_mes,
        'total_pagos_realizados_mes': total_pagos_realizados_mes,
        'cuota_diaria_necesaria': cuota_diaria_necesaria,
        'total_ventas_mes': total_ventas_mes,
        'fechas_pago_pendientes': fechas_pago_pendientes,
        'mes_anterior': mes_anterior,
        'anio_anterior': anio_anterior,
        'mes_siguiente': mes_siguiente,
        'anio_siguiente': anio_siguiente,
        'dias_semana': ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'],
        'folio_busqueda': folio_busqueda,
        'facturas_filtradas': facturas_filtradas,
        'fechas_factura_filtrada': fechas_factura_filtrada,
    }

def obtener_saldo_global(user):
    return svc_saldo_global(user)
