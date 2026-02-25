from django.db import models
from proveedores.models import Proveedores
# Create your models here.
class Facturas(models.Model):
    ESTADOS = [
        ('PENDIENTE', 'Pendiente'),
        ('PAGADO', 'Pagado'),
        ('ABONADO', 'Abonado'),
    ]
    TIPOS = [
        ('FACTURA', 'Factura'),
        ('REMISION', 'Remision'),
        ('GASTOS_GENERALES', 'Gastos Generales'),
    ]
    CUENTA_OVERRIDE_OPCIONES = [
        ('PROVEEDOR', 'Cuenta del Proveedor'),
        ('MAESTRA',   'Cuenta Maestra'),
    ]

    proveedor = models.ForeignKey(Proveedores, on_delete=models.CASCADE)
    folio = models.CharField(max_length=200, blank=True, null=True) #FOLIO
    notas = models.TextField(blank=True, null=True)
    monto = models.DecimalField(max_digits=15, decimal_places=2)#esto representa el monto total de la factura
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    tipo = models.CharField(max_length=20, choices=TIPOS, default='FACTURA')
    organizacion = models.ForeignKey('users.Organizacion', on_delete=models.CASCADE)

    # Selección manual de la cuenta a mostrar en PDF y detalle día
    cuenta_override = models.CharField(
        max_length=20,
        choices=CUENTA_OVERRIDE_OPCIONES,
        default='PROVEEDOR',
        verbose_name='Cuenta a mostrar',
        help_text='Elige qué cuenta bancaria se muestra en el PDF y en el detalle del día.',
    )

    @property
    def cuenta_a_mostrar(self):
        """
        Devuelve (cuenta_str, etiqueta) para usar en detalle_dia y PDF.
        Siempre usa la selección manual del campo cuenta_override.
        """
        proveedor = self.proveedor
        if not proveedor:
            return ('Sin Cuenta', '')

        if self.cuenta_override == 'MAESTRA':
            if proveedor.cuenta_maestra:
                return (
                    proveedor.cuenta_maestra.cuenta or 'S/C',
                    f'Cuenta Maestra: {proveedor.cuenta_maestra.nombre}'
                )
            return ('S/C', 'Cuenta Maestra no configurada')

        # PROVEEDOR (default)
        return (proveedor.cuenta or 'S/C', 'Cuenta Proveedor')


class FacturasFechasDePago(models.Model):
    factura = models.ForeignKey(Facturas, on_delete=models.CASCADE)
    fecha_por_pagar = models.DateField()
    monto_por_pagar = models.DecimalField(max_digits=15, decimal_places=2)#monto por pagar en esa fecha
