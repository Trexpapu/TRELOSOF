from django.db import models
from django.utils import timezone
from facturas.models import Facturas
from sucursales.models import Ventas
# Create your models here.


class Movimientos_Cartera(models.Model):
    
    ORIGENES = [
        ('CARGO', 'Cargo'),
        ('INGRESO', 'Ingreso'),
        ('PAGO', 'Pago'),
        ('AJUSTE_SUMA', 'Ajuste (Suma)'),
        ('AJUSTE_RESTA', 'Ajuste (Resta)'),
    ]
    origen = models.CharField(max_length=20, choices=ORIGENES)
    monto = models.DecimalField(max_digits=15, decimal_places=2)
    fecha = models.DateField(default=timezone.now)
    descripcion = models.TextField(blank=True, null=True)
    factura = models.ForeignKey(Facturas, on_delete=models.CASCADE, blank=True, null=True)
    venta = models.ForeignKey(Ventas, on_delete=models.CASCADE, blank=True, null=True)
    fecha_pago_instancia = models.ForeignKey('facturas.FacturasFechasDePago', on_delete=models.CASCADE, null=True, blank=True, related_name='movimientos')
    organizacion = models.ForeignKey('users.Organizacion', on_delete=models.CASCADE, null=True, blank=True)
    
    