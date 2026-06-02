from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from .models import (
    CanalCobro,
    ConceptoIngreso,
    EsquemaComision,
    Ingreso,
    MetodoPago,
    OrigenIngreso,
)


class LedgerComisionesTests(TestCase):
    def setUp(self):
        self.metodo_tarjeta = MetodoPago.objects.create(nombre="Tarjeta")
        self.metodo_efectivo = MetodoPago.objects.create(nombre="Efectivo")
        self.canal_tap = CanalCobro.objects.create(
            nombre="Mercado Pago Tap",
            metodo_pago=self.metodo_tarjeta,
        )
        self.canal_point = CanalCobro.objects.create(
            nombre="Mercado Pago Point",
            metodo_pago=self.metodo_tarjeta,
        )
        self.canal_caja = CanalCobro.objects.create(
            nombre="Efectivo en caja",
            metodo_pago=self.metodo_efectivo,
        )
        self.concepto = ConceptoIngreso.objects.create(nombre="Consulta")
        self.origen = OrigenIngreso.objects.create(nombre="Consultorio")

    def crear_ingreso(self, **kwargs):
        datos = {
            "fecha": timezone.now(),
            "monto_bruto": Decimal("300.00"),
            "concepto": self.concepto,
            "metodo_pago": self.metodo_tarjeta,
            "origen": self.origen,
        }
        datos.update(kwargs)
        return Ingreso.objects.create(**datos)

    def test_esquema_sin_iva_usa_porcentaje_base(self):
        esquema = EsquemaComision.objects.create(
            canal_cobro=self.canal_tap,
            nombre="Comisión sin IVA",
            porcentaje_base=Decimal("2.9900"),
            cobra_iva=False,
        )

        self.assertEqual(esquema.porcentaje_total, Decimal("2.9900"))

    def test_esquema_con_iva_calcula_porcentaje_total(self):
        esquema = EsquemaComision.objects.create(
            canal_cobro=self.canal_tap,
            nombre="Comisión 2.99% + IVA",
            porcentaje_base=Decimal("2.9900"),
            cobra_iva=True,
        )

        self.assertEqual(esquema.porcentaje_total, Decimal("3.4684"))

    def test_ingreso_sin_esquema_de_comision_no_descuenta_comision(self):
        ingreso = self.crear_ingreso(
            metodo_pago=self.metodo_efectivo,
            canal_cobro=self.canal_caja,
        )

        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("0.0000"))
        self.assertEqual(ingreso.comision, Decimal("0.00"))
        self.assertEqual(ingreso.monto_neto, Decimal("300.00"))

    def test_ingreso_con_mercado_pago_tap_299_mas_iva(self):
        esquema = EsquemaComision.objects.create(
            canal_cobro=self.canal_tap,
            nombre="Tap 2.99% + IVA",
            porcentaje_base=Decimal("2.9900"),
            cobra_iva=True,
        )

        ingreso = self.crear_ingreso(
            canal_cobro=self.canal_tap,
            esquema_comision=esquema,
        )

        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("3.4684"))
        self.assertEqual(ingreso.comision, Decimal("10.41"))
        self.assertEqual(ingreso.monto_neto, Decimal("289.59"))

    def test_ingreso_con_mercado_pago_point_35_mas_iva(self):
        esquema = EsquemaComision.objects.create(
            canal_cobro=self.canal_point,
            nombre="Point 3.5% + IVA",
            porcentaje_base=Decimal("3.5000"),
            cobra_iva=True,
        )

        ingreso = self.crear_ingreso(
            canal_cobro=self.canal_point,
            esquema_comision=esquema,
        )

        self.assertEqual(esquema.porcentaje_total, Decimal("4.0600"))
        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("12.18"))
        self.assertEqual(ingreso.monto_neto, Decimal("287.82"))

    def test_ingreso_con_comision_manual_no_sobrescribe_comision(self):
        esquema = EsquemaComision.objects.create(
            canal_cobro=self.canal_tap,
            nombre="Tap 2.99% + IVA",
            porcentaje_base=Decimal("2.9900"),
            cobra_iva=True,
        )

        ingreso = self.crear_ingreso(
            canal_cobro=self.canal_tap,
            esquema_comision=esquema,
            comision_manual=True,
            comision=Decimal("15.00"),
        )

        self.assertEqual(ingreso.comision, Decimal("15.00"))
        self.assertEqual(ingreso.monto_neto, Decimal("285.00"))
        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("5.0000"))
