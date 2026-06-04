from decimal import Decimal

from django.core.exceptions import ValidationError
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
        self.canal_point_air = CanalCobro.objects.create(
            nombre="Mercado Pago Point Air",
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

    def crear_esquema_mercado_pago_35(self):
        esquema = EsquemaComision.objects.create(
            nombre="Mercado Pago 3.5% + IVA",
            porcentaje_base=Decimal("3.5000"),
            cobra_iva=True,
        )
        esquema.canales_cobro.add(self.canal_tap, self.canal_point_air)
        return esquema

    def crear_esquema_tap_299(self):
        esquema = EsquemaComision.objects.create(
            nombre="Tap 2.99% + IVA",
            porcentaje_base=Decimal("2.9900"),
            cobra_iva=True,
        )
        esquema.canales_cobro.add(self.canal_tap)
        return esquema

    def test_esquema_sin_iva_usa_porcentaje_base(self):
        esquema = EsquemaComision.objects.create(
            nombre="Comisión sin IVA",
            porcentaje_base=Decimal("2.9900"),
            cobra_iva=False,
        )

        self.assertEqual(esquema.porcentaje_total, Decimal("2.9900"))

    def test_esquema_con_iva_calcula_porcentaje_total(self):
        esquema = self.crear_esquema_tap_299()

        self.assertEqual(esquema.porcentaje_total, Decimal("3.4684"))

    def test_un_mismo_esquema_puede_asociarse_a_tap_y_point_air(self):
        esquema = self.crear_esquema_mercado_pago_35()

        self.assertEqual(esquema.canales_cobro.count(), 2)
        self.assertIn(self.canal_tap, esquema.canales_cobro.all())
        self.assertIn(self.canal_point_air, esquema.canales_cobro.all())
        self.assertEqual(esquema.porcentaje_total, Decimal("4.0600"))

    def test_ingreso_sin_esquema_de_comision_no_descuenta_comision(self):
        ingreso = self.crear_ingreso(
            metodo_pago=self.metodo_efectivo,
            canal_cobro=self.canal_caja,
        )

        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("0.0000"))
        self.assertEqual(ingreso.comision, Decimal("0.00"))
        self.assertEqual(ingreso.monto_neto, Decimal("300.00"))

    def test_ingreso_tap_usa_esquema_compartido_y_calcula_comision(self):
        esquema = self.crear_esquema_mercado_pago_35()

        ingreso = self.crear_ingreso(
            canal_cobro=self.canal_tap,
            esquema_comision=esquema,
        )

        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("12.18"))
        self.assertEqual(ingreso.monto_neto, Decimal("287.82"))

    def test_ingreso_point_air_usa_mismo_esquema_y_calcula_comision(self):
        esquema = self.crear_esquema_mercado_pago_35()

        ingreso = self.crear_ingreso(
            canal_cobro=self.canal_point_air,
            esquema_comision=esquema,
        )

        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("12.18"))
        self.assertEqual(ingreso.monto_neto, Decimal("287.82"))

    def test_editar_solo_notas_no_recalcula_comision_historica(self):
        esquema = self.crear_esquema_mercado_pago_35()
        ingreso = self.crear_ingreso(
            canal_cobro=self.canal_tap,
            esquema_comision=esquema,
        )

        esquema.porcentaje_base = Decimal("10.0000")
        esquema.save()
        ingreso.notas = "Nota administrativa sin impacto en la comisión"
        ingreso.save()
        ingreso.refresh_from_db()

        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("12.18"))
        self.assertEqual(ingreso.monto_neto, Decimal("287.82"))

    def test_cambiar_monto_bruto_recalcula_comision(self):
        esquema = self.crear_esquema_mercado_pago_35()
        ingreso = self.crear_ingreso(
            canal_cobro=self.canal_tap,
            esquema_comision=esquema,
        )

        ingreso.monto_bruto = Decimal("600.00")
        ingreso.save()
        ingreso.refresh_from_db()

        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("24.36"))
        self.assertEqual(ingreso.monto_neto, Decimal("575.64"))

    def test_cambiar_esquema_comision_recalcula_comision(self):
        esquema_tap = self.crear_esquema_tap_299()
        esquema_compartido = self.crear_esquema_mercado_pago_35()
        ingreso = self.crear_ingreso(
            canal_cobro=self.canal_tap,
            esquema_comision=esquema_tap,
        )

        ingreso.esquema_comision = esquema_compartido
        ingreso.save()
        ingreso.refresh_from_db()

        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("12.18"))
        self.assertEqual(ingreso.monto_neto, Decimal("287.82"))

    def test_ingreso_con_comision_manual_no_sobrescribe_comision(self):
        esquema = self.crear_esquema_mercado_pago_35()

        ingreso = self.crear_ingreso(
            canal_cobro=self.canal_tap,
            esquema_comision=esquema,
            comision_manual=True,
            comision=Decimal("15.00"),
        )

        esquema.porcentaje_base = Decimal("10.0000")
        esquema.save()
        ingreso.notas = "La comisión manual debe conservarse"
        ingreso.save()
        ingreso.refresh_from_db()

        self.assertEqual(ingreso.comision, Decimal("15.00"))
        self.assertEqual(ingreso.monto_neto, Decimal("285.00"))
        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("5.0000"))

    def test_clean_valida_que_esquema_pertenezca_al_canal(self):
        esquema = self.crear_esquema_tap_299()
        ingreso = self.crear_ingreso(
            canal_cobro=self.canal_point_air,
            esquema_comision=esquema,
        )

        with self.assertRaises(ValidationError):
            ingreso.clean()
