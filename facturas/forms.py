from django import forms
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime
from .models import Facturas
from proveedores.models import Proveedores

class BaseFacturaForm(forms.ModelForm):
    """
    Formulario base con lógica común de validación de formatos.
    """
    fechas_pago = forms.CharField(
        required=True,
        widget=forms.HiddenInput()
    )

    montos_pago = forms.CharField(
        required=True,
        widget=forms.HiddenInput()
    )

    distribucion_igual = forms.BooleanField(
        required=False,
        initial=False,
        label="Distribuir equitativamente"
    )

    class Meta:
        model = Facturas
        fields = ['proveedor', 'folio', 'tipo', 'monto', 'notas', 'cuenta_override']
        
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and user.organizacion:
             self.fields['proveedor'].queryset = Proveedores.objects.filter(organizacion=user.organizacion)
        else:
             self.fields['proveedor'].queryset = Proveedores.objects.none()


    def clean_monto(self):
        monto = self.cleaned_data.get('monto')
        if monto is not None and monto <= 0:
            raise ValidationError('El monto debe ser mayor a cero.')
        return monto

    def clean_fechas_pago(self):
        raw = self.cleaned_data.get('fechas_pago', '').strip()

        if not raw:
            raise ValidationError('Debe registrar al menos una fecha de pago.')

        fechas = []

        for f in raw.split(','):
            f = f.strip()
            if not f:
                continue

            try:
                fecha_obj = datetime.strptime(f, '%Y-%m-%d').date()
                fechas.append(fecha_obj)
            except ValueError:
                raise ValidationError(f'Fecha inválida: {f}')

        if not fechas:
            raise ValidationError('Debe registrar al menos una fecha de pago.')

        if len(set(fechas)) != len(fechas):
            raise ValidationError('No se permiten fechas de pago duplicadas.')

        return fechas

    def clean_montos_pago(self):
        raw = self.cleaned_data.get('montos_pago', '').strip()
        
        # Si venía vacío pero fecha venía llena, se podría desincronizar.
        # Pero suponemos que JS manda paridad.
        
        if not raw:
             raise ValidationError('Debe registrar al menos un monto de pago.')

        montos = []

        for m in raw.split(','):
            m = m.strip()
            if not m:
                continue

            try:
                monto = Decimal(m)
            except Exception:
                raise ValidationError(f'Monto inválido: {m}')

            if monto <= 0:
                raise ValidationError('Todos los montos deben ser mayores a cero.')

            montos.append(monto)

        if not montos:
            raise ValidationError('Debe registrar al menos un monto de pago.')

        return montos


class FacturaCreateForm(BaseFacturaForm):
    """
    Formulario de creación de facturas.
    Hereda toda la validación de formatos de BaseFacturaForm.
    """
    pass


class FacturaEditForm(BaseFacturaForm):
    """
    Formulario de edición de facturas.
    Hereda toda la validación de formatos de BaseFacturaForm.
    """
    pass
