from django.db.models import Sum, Q, Count
from decimal import Decimal
from ..models import Movimientos_Cartera

def obtener_saldo_global(user):
    """
    Obtiene el saldo global de la organización del usuario.
    Ingresos (Ventas) - Egresos (Pagos generales, gastos, etc)
    """
    if not user or not user.organizacion:
        return Decimal('0.00')

    resultado = Movimientos_Cartera.objects.filter(organizacion=user.organizacion).aggregate(
        ingresos=Sum('monto', filter=Q(origen='INGRESO')),
        pagos=Sum('monto', filter=Q(origen='PAGO')),
        ajuste_suma=Sum('monto', filter=Q(origen='AJUSTE_SUMA')),
        ajuste_resta=Sum('monto', filter=Q(origen='AJUSTE_RESTA')),
    )
    
    ingresos = resultado['ingresos'] or Decimal('0')
    pagos = resultado['pagos'] or Decimal('0')
    ajuste_suma = resultado['ajuste_suma'] or Decimal('0')
    ajuste_resta = resultado['ajuste_resta'] or Decimal('0')
    
    # Saldo = (Ingresos + Ajustes Suma) - (Pagos + Ajustes Resta)
    # Nota: Los 'pagos' restan al saldo disponible.
    return (ingresos + ajuste_suma) - (pagos + ajuste_resta)

def obtener_cargo_total(user):
    """
    Calcula cuánto debemos a proveedores en total (Deuda Total Organzación).
    (Total Cargos de Facturas - Total Pagos a Facturas)
    """
    if not user or not user.organizacion:
        return Decimal('0.00')

    # Filtramos solo movimientos relacionados con facturas Y de la organización
    resultado = Movimientos_Cartera.objects.filter(
        factura__isnull=False,
        organizacion=user.organizacion
    ).aggregate(
        cargos=Sum('monto', filter=Q(origen='CARGO')),
        pagos=Sum('monto', filter=Q(origen='PAGO'))
    )
    
    cargos = resultado['cargos'] or Decimal('0')
    pagos = resultado['pagos'] or Decimal('0')
    
    return cargos - pagos

def obtener_pagos_del_dia(fecha, user):
    """
    Obtiene el total y el contador de pagos de un día específico para la organización.
    """
    if not user or not user.organizacion:
        return Decimal('0.00'), 0

    resultado = Movimientos_Cartera.objects.filter(
        fecha=fecha,
        origen='PAGO',
        organizacion=user.organizacion
    ).aggregate(
        total=Sum('monto'),
        contador=Count('id')
    )

    total = resultado['total'] or Decimal('0')
    contador = resultado['contador']

    return total, contador

def obtener_saldo_factura(factura):
    """
    Calcula el saldo pendiente de una factura específica.
    Saldo = Cargo Original - Suma de Pagos
    Retorna: Decimal (Saldo pendiente)
    """
    # No requerimos user aquí si asumimos que la factura ya fue validada por el caller
    # al obtenerla.
    resultado = Movimientos_Cartera.objects.filter(factura=factura).aggregate(
        cargo=Sum('monto', filter=Q(origen='CARGO')),
        pagos=Sum('monto', filter=Q(origen='PAGO'))
    )

    cargo = resultado['cargo'] or Decimal('0')
    pagos = resultado['pagos'] or Decimal('0')

    return cargo - pagos