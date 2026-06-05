from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import (
    CanalCobro,
    ConceptoIngreso,
    EsquemaComision,
    GastoMaterial,
    Ingreso,
    MetodoPago,
    OrigenIngreso,
)


class LedgerComisionesTests(TestCase):
    def setUp(self):
        self.metodo_tarjeta = MetodoPago.objects.create(nombre="Tarjeta")
        self.metodo_efectivo = MetodoPago.objects.create(nombre="Efectivo")
        self.metodo_transferencia = MetodoPago.objects.create(nombre="Transferencia")

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
        self.canal_spei = CanalCobro.objects.create(
            nombre="SPEI / Transferencia bancaria",
            metodo_pago=self.metodo_transferencia,
        )

        self.esquema_sin_comision = EsquemaComision.objects.create(
            nombre="Sin comisión 0%",
            porcentaje_base=Decimal("0.0000"),
            cobra_iva=False,
        )
        self.esquema_sin_comision.canales_cobro.add(self.canal_caja, self.canal_spei)

        self.esquema_mercado_pago = EsquemaComision.objects.create(
            nombre="Mercado Pago 3.5% + IVA",
            porcentaje_base=Decimal("3.5000"),
            cobra_iva=True,
        )
        self.esquema_mercado_pago.canales_cobro.add(
            self.canal_tap,
            self.canal_point_air,
        )

        self.canal_caja.esquema_comision_predeterminado = self.esquema_sin_comision
        self.canal_caja.save()
        self.canal_spei.esquema_comision_predeterminado = self.esquema_sin_comision
        self.canal_spei.save()
        self.canal_tap.esquema_comision_predeterminado = self.esquema_mercado_pago
        self.canal_tap.save()
        self.canal_point_air.esquema_comision_predeterminado = self.esquema_mercado_pago
        self.canal_point_air.save()

        self.concepto = ConceptoIngreso.objects.create(nombre="Consulta")
        self.concepto_material = ConceptoIngreso.objects.create(
            nombre="Consulta con material",
            incluye_material=True,
            monto_material_sugerido=Decimal("50.00"),
        )
        self.origen = OrigenIngreso.objects.create(nombre="Consultorio")

    def crear_ingreso(self, **kwargs):
        datos = {
            "fecha": timezone.now(),
            "monto_bruto": Decimal("300.00"),
            "concepto": self.concepto,
            "canal_cobro": self.canal_tap,
            "origen": self.origen,
        }
        datos.update(kwargs)
        return Ingreso.objects.create(**datos)

    def crear_esquema_tap_299(self):
        esquema = EsquemaComision.objects.create(
            nombre="Tap 2.99% + IVA",
            porcentaje_base=Decimal("2.9900"),
            cobra_iva=True,
        )
        esquema.canales_cobro.add(self.canal_tap)
        return esquema

    def test_esquema_sin_iva_usa_porcentaje_base(self):
        self.assertEqual(
            self.esquema_sin_comision.porcentaje_total,
            Decimal("0.0000"),
        )

    def test_esquema_con_iva_calcula_porcentaje_total(self):
        self.assertEqual(
            self.esquema_mercado_pago.porcentaje_total,
            Decimal("4.0600"),
        )

    def test_un_mismo_esquema_puede_asociarse_a_tap_y_point_air(self):
        self.assertEqual(self.esquema_mercado_pago.canales_cobro.count(), 2)
        self.assertIn(self.canal_tap, self.esquema_mercado_pago.canales_cobro.all())
        self.assertIn(
            self.canal_point_air,
            self.esquema_mercado_pago.canales_cobro.all(),
        )

    def test_ingreso_efectivo_usa_esquema_predeterminado_sin_comision(self):
        ingreso = self.crear_ingreso(canal_cobro=self.canal_caja)

        self.assertEqual(ingreso.metodo_pago, self.metodo_efectivo)
        self.assertEqual(ingreso.esquema_comision, self.esquema_sin_comision)
        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("0.0000"))
        self.assertEqual(ingreso.comision, Decimal("0.00"))
        self.assertEqual(ingreso.monto_neto, Decimal("300.00"))

    def test_ingreso_spei_usa_esquema_predeterminado_sin_comision(self):
        ingreso = self.crear_ingreso(canal_cobro=self.canal_spei)

        self.assertEqual(ingreso.metodo_pago, self.metodo_transferencia)
        self.assertEqual(ingreso.esquema_comision, self.esquema_sin_comision)
        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("0.0000"))
        self.assertEqual(ingreso.comision, Decimal("0.00"))
        self.assertEqual(ingreso.monto_neto, Decimal("300.00"))

    def test_ingreso_tap_usa_esquema_predeterminado_y_calcula_comision(self):
        ingreso = self.crear_ingreso(canal_cobro=self.canal_tap)

        self.assertEqual(ingreso.metodo_pago, self.metodo_tarjeta)
        self.assertEqual(ingreso.esquema_comision, self.esquema_mercado_pago)
        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("12.18"))
        self.assertEqual(ingreso.monto_neto, Decimal("287.82"))

    def test_ingreso_point_air_usa_mismo_esquema_y_calcula_comision(self):
        ingreso = self.crear_ingreso(canal_cobro=self.canal_point_air)

        self.assertEqual(ingreso.esquema_comision, self.esquema_mercado_pago)
        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("12.18"))
        self.assertEqual(ingreso.monto_neto, Decimal("287.82"))

    def test_ingreso_sin_esquema_explicito_asigna_predeterminado(self):
        ingreso = self.crear_ingreso(canal_cobro=self.canal_tap)

        self.assertEqual(ingreso.esquema_comision, self.esquema_mercado_pago)

    def test_clean_valida_que_esquema_pertenezca_al_canal(self):
        esquema_tap = self.crear_esquema_tap_299()
        ingreso = Ingreso(
            fecha=timezone.now(),
            monto_bruto=Decimal("300.00"),
            concepto=self.concepto,
            canal_cobro=self.canal_point_air,
            esquema_comision=esquema_tap,
            origen=self.origen,
        )

        with self.assertRaises(ValidationError):
            ingreso.clean()

    def test_save_falla_si_canal_no_tiene_esquema_predeterminado_ni_explicito(self):
        canal_sin_predeterminado = CanalCobro.objects.create(
            nombre="Canal sin esquema",
            metodo_pago=self.metodo_efectivo,
        )

        with self.assertRaises(ValidationError):
            self.crear_ingreso(canal_cobro=canal_sin_predeterminado)

    def test_editar_solo_notas_no_recalcula_comision_historica(self):
        ingreso = self.crear_ingreso(canal_cobro=self.canal_tap)

        self.esquema_mercado_pago.porcentaje_base = Decimal("10.0000")
        self.esquema_mercado_pago.save()
        ingreso.notas = "Nota administrativa sin impacto en la comisión"
        ingreso.save()
        ingreso.refresh_from_db()

        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("12.18"))
        self.assertEqual(ingreso.monto_neto, Decimal("287.82"))

    def test_cambiar_monto_bruto_recalcula_comision(self):
        ingreso = self.crear_ingreso(canal_cobro=self.canal_tap)

        ingreso.monto_bruto = Decimal("600.00")
        ingreso.save()
        ingreso.refresh_from_db()

        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("24.36"))
        self.assertEqual(ingreso.monto_neto, Decimal("575.64"))

    def test_cambiar_esquema_comision_recalcula_comision(self):
        esquema_tap = self.crear_esquema_tap_299()
        ingreso = self.crear_ingreso(
            canal_cobro=self.canal_tap,
            esquema_comision=esquema_tap,
        )

        ingreso.esquema_comision = self.esquema_mercado_pago
        ingreso.save()
        ingreso.refresh_from_db()

        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("12.18"))
        self.assertEqual(ingreso.monto_neto, Decimal("287.82"))

    def test_ingreso_con_comision_manual_no_sobrescribe_comision(self):
        ingreso = self.crear_ingreso(
            canal_cobro=self.canal_tap,
            comision_manual=True,
            comision=Decimal("15.00"),
        )

        self.esquema_mercado_pago.porcentaje_base = Decimal("10.0000")
        self.esquema_mercado_pago.save()
        ingreso.notas = "La comisión manual debe conservarse"
        ingreso.save()
        ingreso.refresh_from_db()

        self.assertEqual(ingreso.comision, Decimal("15.00"))
        self.assertEqual(ingreso.monto_neto, Decimal("285.00"))
        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("5.0000"))


    def test_gasto_material_aumenta_pool(self):
        GastoMaterial.objects.create(
            fecha=timezone.now(),
            monto=Decimal("500.00"),
            descripcion="Material de curación",
        )

        self.assertEqual(Ingreso.calcular_pool_material_actual(), Decimal("500.00"))

    def test_ingreso_material_menor_que_pool_recupera_y_reduce_pool(self):
        GastoMaterial.objects.create(
            fecha=timezone.now(),
            monto=Decimal("500.00"),
            descripcion="Material de curación",
        )

        ingreso = self.crear_ingreso(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("50.00"),
        )

        self.assertEqual(ingreso.pool_material_antes, Decimal("500.00"))
        self.assertEqual(ingreso.material_recuperado, Decimal("50.00"))
        self.assertEqual(ingreso.material_excedente, Decimal("0.00"))
        self.assertEqual(ingreso.pool_material_despues, Decimal("450.00"))
        self.assertEqual(Ingreso.calcular_pool_material_actual(), Decimal("450.00"))

    def test_ingreso_material_mayor_que_pool_genera_excedente(self):
        GastoMaterial.objects.create(
            fecha=timezone.now(),
            monto=Decimal("20.00"),
            descripcion="Material de curación",
        )

        ingreso = self.crear_ingreso(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("50.00"),
        )

        self.assertEqual(ingreso.pool_material_antes, Decimal("20.00"))
        self.assertEqual(ingreso.material_recuperado, Decimal("20.00"))
        self.assertEqual(ingreso.material_excedente, Decimal("30.00"))
        self.assertEqual(ingreso.pool_material_despues, Decimal("0.00"))
        self.assertEqual(Ingreso.calcular_pool_material_actual(), Decimal("0.00"))

    def test_ingreso_material_con_pool_cero_genera_todo_excedente(self):
        ingreso = self.crear_ingreso(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("50.00"),
        )

        self.assertEqual(ingreso.pool_material_antes, Decimal("0.00"))
        self.assertEqual(ingreso.material_recuperado, Decimal("0.00"))
        self.assertEqual(ingreso.material_excedente, Decimal("50.00"))
        self.assertEqual(ingreso.pool_material_despues, Decimal("0.00"))

    def test_editar_solo_notas_no_recalcula_material_historico(self):
        GastoMaterial.objects.create(
            fecha=timezone.now(),
            monto=Decimal("500.00"),
            descripcion="Material de curación",
        )
        ingreso = self.crear_ingreso(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("50.00"),
        )

        GastoMaterial.objects.create(
            fecha=timezone.now(),
            monto=Decimal("100.00"),
            descripcion="Material posterior",
        )
        ingreso.notas = "Editar notas no debe recalcular material"
        ingreso.save()
        ingreso.refresh_from_db()

        self.assertEqual(ingreso.pool_material_antes, Decimal("500.00"))
        self.assertEqual(ingreso.material_recuperado, Decimal("50.00"))
        self.assertEqual(ingreso.material_excedente, Decimal("0.00"))
        self.assertEqual(ingreso.pool_material_despues, Decimal("450.00"))

    def test_cambiar_monto_material_cobrado_recalcula_material(self):
        GastoMaterial.objects.create(
            fecha=timezone.now(),
            monto=Decimal("500.00"),
            descripcion="Material de curación",
        )
        ingreso = self.crear_ingreso(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("50.00"),
        )

        ingreso.monto_material_cobrado = Decimal("120.00")
        ingreso.save()
        ingreso.refresh_from_db()

        self.assertEqual(ingreso.pool_material_antes, Decimal("500.00"))
        self.assertEqual(ingreso.material_recuperado, Decimal("120.00"))
        self.assertEqual(ingreso.material_excedente, Decimal("0.00"))
        self.assertEqual(ingreso.pool_material_despues, Decimal("380.00"))

    def test_no_permite_material_cobrado_si_concepto_no_incluye_material(self):
        with self.assertRaises(ValidationError):
            self.crear_ingreso(
                concepto=self.concepto,
                monto_material_cobrado=Decimal("50.00"),
            )

    def test_permite_concepto_con_material_sin_material_cobrado(self):
        ingreso = self.crear_ingreso(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("0.00"),
        )

        self.assertEqual(ingreso.monto_material_cobrado, Decimal("0.00"))
        self.assertEqual(ingreso.material_recuperado, Decimal("0.00"))
        self.assertEqual(ingreso.material_excedente, Decimal("0.00"))
