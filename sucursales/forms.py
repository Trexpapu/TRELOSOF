# forms.py
from django import forms
from .models import Sucursales, Ventas


class SucursalForm(forms.ModelForm):
    class Meta:
        model = Sucursales
        fields = ['nombre', 'direccion']

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        if not nombre or not nombre.strip():
            raise forms.ValidationError('El nombre no puede estar vacío.')
        return nombre


class VentaForm(forms.ModelForm):
    class Meta:
        model = Ventas
        fields = ['fecha', 'monto', 'sucursal']
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(VentaForm, self).__init__(*args, **kwargs)
        if user and user.organizacion:
            self.fields['sucursal'].queryset = Sucursales.objects.filter(organizacion=user.organizacion)
        else:
            self.fields['sucursal'].queryset = Sucursales.objects.none()

    def clean_monto(self):
        monto = self.cleaned_data.get('monto')
        if monto is not None and monto <= 0:
            raise forms.ValidationError('El monto debe ser mayor a cero.')
        return monto
