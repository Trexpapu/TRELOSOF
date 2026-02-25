from django.db import models

# Create your models here.
class Proveedores(models.Model):
    nombre = models.CharField(max_length=200)
    cuenta = models.TextField(blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    cuenta_maestra = models.ForeignKey('Cuenta_Maestra', on_delete=models.PROTECT, blank=True, null=True)
    organizacion = models.ForeignKey('users.Organizacion', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.nombre

class Cuenta_Maestra(models.Model):
    nombre = models.CharField(max_length=200)
    cuenta = models.TextField(blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    organizacion = models.ForeignKey('users.Organizacion', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.nombre