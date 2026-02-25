from django import forms
from django.core.exceptions import ValidationError
from .models import Movimientos_Cartera
from .services.movimientos import servicio_obtener_monto_restante_por_pagar_factura
class PagoForm(forms.ModelForm):
    class Meta:
        model = Movimientos_Cartera
        fields = ['monto']

    def __init__(self, *args, factura=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.factura = factura

    def clean(self):
        cleaned_data = super().clean()
        monto = cleaned_data.get('monto')

        if not monto or not self.factura:
            return cleaned_data

        

        return cleaned_data


