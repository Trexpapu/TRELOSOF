from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, F
from django.db.models.functions import TruncDay
from sucursales.models import Ventas

def reporte_ventas_por_sucursal(fecha_inicio, fecha_fin, user, sucursal_id=None):
    if not user or not user.organizacion:
        return []
        
    qs = Ventas.objects.filter(
        fecha__range=(fecha_inicio, fecha_fin),
        sucursal__organizacion=user.organizacion
    )
    if sucursal_id:
        qs = qs.filter(sucursal_id=sucursal_id)
    
    return list(qs.values('sucursal__nombre')
                .annotate(total_ventas=Sum('monto'))
                .order_by('-total_ventas'))

def reporte_ventas_diarias(fecha_inicio, fecha_fin, user, sucursal_id=None):
    if not user or not user.organizacion:
        return []

    qs = Ventas.objects.filter(
        fecha__range=(fecha_inicio, fecha_fin),
        sucursal__organizacion=user.organizacion
    )
    if sucursal_id:
        qs = qs.filter(sucursal_id=sucursal_id)
    
    return list(qs.annotate(dia=TruncDay('fecha'))
                .values('dia')
                .annotate(total=Sum('monto'))
                .order_by('dia'))

def obtener_alertas_criticas(fecha_inicio, fecha_fin, user, sucursal_id=None, monto_critico=0):
    if not user or not user.organizacion:
        return []

    try:
        monto_critico = Decimal(monto_critico)
    except:
        return []

    if monto_critico <= 0:
        return []
    
    qs = Ventas.objects.filter(
        fecha__range=(fecha_inicio, fecha_fin),
        sucursal__organizacion=user.organizacion
    )
    
    if sucursal_id:
        qs = qs.filter(sucursal_id=sucursal_id)

    daily_branch_sales = (qs.annotate(dia=TruncDay('fecha'))
                          .values('dia', 'sucursal__nombre')
                          .annotate(total=Sum('monto'))
                          .filter(total__lt=monto_critico)
                          .order_by('dia', 'sucursal__nombre'))
    
    return list(daily_branch_sales)