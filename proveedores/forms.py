from django import forms
from .models import Proveedores, Cuenta_Maestra

class ProveedorForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(ProveedorForm, self).__init__(*args, **kwargs)
        if user and user.organizacion:
            self.fields['cuenta_maestra'].queryset = Cuenta_Maestra.objects.filter(organizacion=user.organizacion)
        else:
            self.fields['cuenta_maestra'].queryset = Cuenta_Maestra.objects.none()

    class Meta:
        model = Proveedores
        fields = ['nombre', 'cuenta', 'telefono', 'email', 'cuenta_maestra']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Nombre del proveedor'
            }),
            'cuenta': forms.Textarea(attrs={
                'class': 'form-textarea',
                'placeholder': 'Información de cuenta bancaria',
                'rows': 3
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Teléfono de contacto'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'correo@ejemplo.com'
            }),
            'cuenta_maestra': forms.Select(attrs={
                'class': 'form-input',
            })
        }
        labels = {
            'nombre': 'Nombre completo',
            'cuenta': 'Datos de cuenta bancaria',
            'telefono': 'Teléfono',
            'email': 'Correo electrónico',
            'cuenta_maestra': 'Cuenta Maestra'
        }
    def clean_telefono(self):
        # Obtenemos el valor. Si es None o vacío, aquí se detiene el problema.
        telefono = self.cleaned_data.get('telefono')

        # Si el campo está vacío (es None o ''), simplemente lo devolvemos
        if not telefono:
            return telefono

        # Ahora es seguro usar métodos de string porque sabemos que no es None
        telefono = telefono.replace(" ", "")

        # Validar que solo tenga números
        if not telefono.isdigit():
            raise forms.ValidationError('El teléfono debe contener solo números.')

        return telefono

class CuentaMaestraForm(forms.ModelForm):
    class Meta:
        model = Cuenta_Maestra
        fields = ['nombre', 'cuenta', 'telefono', 'email']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Nombre de la cuenta maestra'
            }),
            'cuenta': forms.Textarea(attrs={
                'class': 'form-textarea',
                'placeholder': 'Información de cuenta bancaria',
                'rows': 3
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Teléfono de contacto'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'correo@ejemplo.com'
            })
        }
        labels = {
            'nombre': 'Nombre completo',
            'cuenta': 'Datos de cuenta bancaria',
            'telefono': 'Teléfono',
            'email': 'Correo electrónico'
        }
    def clean_telefono(self):
        telefono = self.cleaned_data.get('telefono')
        if not telefono:
            return telefono
        telefono = telefono.replace(" ", "")
        if not telefono.isdigit():
            raise forms.ValidationError('El teléfono debe contener solo números.')
        return telefono
