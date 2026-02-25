from django.urls import path
from .views import *
from django.views.generic import RedirectView, TemplateView

urlpatterns = [
    path('calendario/', calendario_financiero, name='calendario-financiero'),
    path('calendario/dia/<str:fecha_str>/', detalle_dia, name='detalle-dia'),
    path('reporte_ventas_sucursal/', ventas_por_sucursal, name='reporte-ventas-sucursal'),
    path('reportes_facturas/', reporte_facturas, name='reporte-facturas'),
    path('reportes/movimientos/', reporte_movimientos, name='reporte-movimientos'),
    path('exportar_tabulacion/', exportar_tabulacion, name='exportar_tabulacion'),
    
    # Herramientas
    path('herramientas/tabulador/', herramienta_tabulador, name='herramienta-tabulador'),
    path('herramientas/tabulador/exportar/', exportar_tabulacion_simple, name='exportar-tabulacion-simple'),
    
    # Legales
    path('terminos-y-condiciones/', TemplateView.as_view(template_name='core/terminos_condiciones.html'), name='terminos_condiciones'),
    path('politicas-de-privacidad/', TemplateView.as_view(template_name='core/politicas_privacidad.html'), name='politicas_privacidad'),
]
