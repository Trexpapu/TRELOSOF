from django.test import TestCase
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date


from proveedores.models import Proveedores
from facturas.models import Facturas, FacturasFechasDePago
from .services.facturas import servicio_crear_factura_con_fechas
class ServicioCrearFacturaConFechasTest(TestCase):
    def setUp(self):
        self.proveedor = Proveedores.objects.create(
            nombre="Proveedor Test",
            telefono="4431234567"
        )

    def test_error_cuando_suma_pagos_no_coincide(self):
        """
        Debe lanzar ValidationError cuando la suma de los pagos
        no coincide con el monto total de la factura
        """

        data = {
            "factura": {
                "proveedor": self.proveedor,
                "folio": "FAC-ERROR-001",
                "tipo": "FACTURA",
                "monto": Decimal("1000.00"),
                "notas": "Factura con pagos incorrectos"
            },
            "pagos": [
                {
                    "fecha": date(2026, 2, 10),
                    "monto": Decimal("300.00")
                },
                {
                    "fecha": date(2026, 3, 10),
                    "monto": Decimal("400.00")
                }
            ]
        }

        with self.assertRaises(ValidationError) as ctx:
            servicio_crear_factura_con_fechas(data)

        self.assertIn(
            'no coincide con el total de la factura',
            ctx.exception.messages[0]   # aquí sí está el texto plano
        )


        # Asegurar que NO se creó nada
        self.assertEqual(Facturas.objects.count(), 0)

# ... imports ...
from .services.facturas import servicio_editar_factura
from cartera.models import Movimientos_Cartera

class ServicioEditarFacturaTest(TestCase):
    def setUp(self):
        self.proveedor = Proveedores.objects.create(
            nombre="Proveedor Edit",
            telefono="4431234567"
        )
        self.factura = Facturas.objects.create(
            proveedor=self.proveedor,
            folio="FAC-EDIT-001",
            tipo="FACTURA",
            monto=Decimal("1000.00"),
            estado="PENDIENTE"
        )
        # Manually create the movement as the service usually does it distinct from standard create
        Movimientos_Cartera.objects.create(
            origen='CARGO',
            monto=self.factura.monto,
            descripcion=f'Creación de factura con FOLIO {self.factura.folio}',
            factura=self.factura,
        )

    def test_editar_factura_actualiza_movimiento(self):
        # Create initial payment schedules
        FacturasFechasDePago.objects.create(
            factura=self.factura,
            fecha_por_pagar=date(2026, 1, 1),
            monto_por_pagar=Decimal("500.00")
        )
        FacturasFechasDePago.objects.create(
            factura=self.factura,
            fecha_por_pagar=date(2026, 1, 15),
            monto_por_pagar=Decimal("500.00")
        )

        new_data = {
            'proveedor': self.proveedor,
            'folio': 'FAC-EDIT-UPDATED',
            'tipo': 'FACTURA',
            'monto': Decimal("1500.00"),
            'notas': 'Updated',
            'estado': 'PENDIENTE',
            'fechas_pago': [date(2026, 2, 1), date(2026, 2, 15)],
            'montos_pago': [Decimal("750.00"), Decimal("750.00")]
        }
        
        servicio_editar_factura(self.factura, new_data)
        
        self.factura.refresh_from_db()
        self.assertEqual(self.factura.monto, Decimal("1500.00"))
        
        movimiento = Movimientos_Cartera.objects.get(factura=self.factura, origen='CARGO')
        self.assertEqual(movimiento.monto, Decimal("1500.00"))
        
        # Verify payment schedules were replaced
        schedules = FacturasFechasDePago.objects.filter(factura=self.factura).order_by('fecha_por_pagar')
        self.assertEqual(schedules.count(), 2)
        self.assertEqual(schedules[0].fecha_por_pagar, date(2026, 2, 1))
        self.assertEqual(schedules[0].monto_por_pagar, Decimal("750.00"))
