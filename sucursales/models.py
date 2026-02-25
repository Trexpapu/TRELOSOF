from django.db import models

# Create your models here.
class Sucursales(models.Model):

    nombre = models.CharField(max_length=200)
    direccion = models.CharField(max_length=300, blank=True, null=True)
    organizacion = models.ForeignKey('users.Organizacion', on_delete=models.CASCADE, null=True, blank=True)


class Ventas(models.Model):
    fecha = models.DateField()
    monto = models.DecimalField(max_digits=15, decimal_places=2)
    sucursal = models.ForeignKey(Sucursales, on_delete=models.CASCADE)