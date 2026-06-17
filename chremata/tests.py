from decimal import Decimal
from uuid import UUID

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.forms import modelform_factory
from django.test import TestCase
from django.utils import timezone

from .services import cobrar_ticket

from .models import (
    CanalCobro,
    ConceptoIngreso,
    EsquemaComision,
    GastoMaterial,
    Ingreso,
    MetodoPago,
    OrigenIngreso,
    Ticket,
    TicketLinea,
    TicketPago,
)


class CatalogosPublicIdTests(TestCase):
    modelos_catalogo = (
        MetodoPago,
        CanalCobro,
        EsquemaComision,
        ConceptoIngreso,
        OrigenIngreso,
    )

    def crear_metodo_pago(self, sufijo):
        return MetodoPago.objects.create(nombre=f"Método {sufijo}")

    def crear_canal_cobro(self, sufijo):
        metodo = MetodoPago.objects.create(nombre=f"Método canal {sufijo}")
        return CanalCobro.objects.create(
            nombre=f"Canal {sufijo}",
            metodo_pago=metodo,
        )

    def crear_esquema_comision(self, sufijo):
        return EsquemaComision.objects.create(
            nombre=f"Esquema {sufijo}",
            porcentaje_base=Decimal("0.0000"),
        )

    def crear_concepto_ingreso(self, sufijo):
        return ConceptoIngreso.objects.create(nombre=f"Concepto {sufijo}")

    def crear_origen_ingreso(self, sufijo):
        return OrigenIngreso.objects.create(nombre=f"Origen {sufijo}")

    def test_catalogos_generan_public_id_uuid_unico_y_conservan_id_entero(self):
        fabricas = (
            self.crear_metodo_pago,
            self.crear_canal_cobro,
            self.crear_esquema_comision,
            self.crear_concepto_ingreso,
            self.crear_origen_ingreso,
        )

        for fabrica in fabricas:
            with self.subTest(catalogo=fabrica.__name__):
                primero = fabrica("A")
                segundo = fabrica("B")

                self.assertIsInstance(primero.pk, int)
                self.assertIsInstance(primero.public_id, UUID)
                self.assertIsNotNone(primero.public_id)
                self.assertNotEqual(primero.public_id, segundo.public_id)

                public_id_original = primero.public_id
                primero.activo = False
                primero.save()
                primero.refresh_from_db()
                self.assertEqual(primero.public_id, public_id_original)

    def test_public_id_es_unico_y_no_editable_en_cada_modelo(self):
        for modelo in self.modelos_catalogo:
            with self.subTest(catalogo=modelo.__name__):
                campo = modelo._meta.get_field("public_id")

                self.assertTrue(campo.unique)
                self.assertFalse(campo.editable)
                self.assertNotIn(
                    "public_id",
                    modelform_factory(modelo, fields="__all__").base_fields,
                )

    def test_admin_muestra_public_id_como_readonly(self):
        for modelo in self.modelos_catalogo:
            with self.subTest(catalogo=modelo.__name__):
                self.assertIn("public_id", admin.site._registry[modelo].readonly_fields)


class ChremataComisionesTests(TestCase):
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
            permite_material_adicional=True,
            monto_material_sugerido=Decimal("50.00"),
        )
        self.origen = OrigenIngreso.objects.create(nombre="Consultorio")

    def crear_ingreso(self, **kwargs):
        datos = {
            "fecha": timezone.now(),
            "monto_procedimiento": Decimal("300.00"),
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
        self.assertEqual(ingreso.monto_total, Decimal("300.00"))
        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("12.18"))
        self.assertEqual(ingreso.monto_neto, Decimal("287.82"))

    def test_ingreso_con_material_calcula_total_y_comision_sobre_total(self):
        ingreso = self.crear_ingreso(
            monto_procedimiento=Decimal("550.00"),
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("500.00"),
            canal_cobro=self.canal_tap,
        )

        self.assertEqual(ingreso.monto_total, Decimal("1050.00"))
        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("42.63"))
        self.assertEqual(ingreso.monto_neto, Decimal("1007.37"))

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
            monto_procedimiento=Decimal("300.00"),
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

    def test_cambiar_monto_procedimiento_recalcula_comision(self):
        ingreso = self.crear_ingreso(canal_cobro=self.canal_tap)

        ingreso.monto_procedimiento = Decimal("600.00")
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

    def test_comision_manual_con_total_cero_evitar_division_entre_cero(self):
        ingreso = self.crear_ingreso(
            monto_procedimiento=Decimal("0.00"),
            comision_manual=True,
            comision=Decimal("0.00"),
        )

        self.assertEqual(ingreso.monto_total, Decimal("0.00"))
        self.assertEqual(ingreso.monto_neto, Decimal("0.00"))
        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("0.0000"))

    def test_ingreso_con_comision_manual_usa_total_con_material(self):
        ingreso = self.crear_ingreso(
            monto_procedimiento=Decimal("550.00"),
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("500.00"),
            canal_cobro=self.canal_tap,
            comision_manual=True,
            comision=Decimal("42.00"),
        )

        self.esquema_mercado_pago.porcentaje_base = Decimal("10.0000")
        self.esquema_mercado_pago.save()
        ingreso.notas = "La comisión manual debe conservarse"
        ingreso.save()
        ingreso.refresh_from_db()

        self.assertEqual(ingreso.monto_total, Decimal("1050.00"))
        self.assertEqual(ingreso.comision, Decimal("42.00"))
        self.assertEqual(ingreso.monto_neto, Decimal("1008.00"))
        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0000"))

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
        self.esquema_mercado_pago.porcentaje_base = Decimal("10.0000")
        self.esquema_mercado_pago.save()
        ingreso.notas = "Editar notas no debe recalcular comisión ni material"
        ingreso.save()
        ingreso.refresh_from_db()

        self.assertEqual(ingreso.pool_material_antes, Decimal("500.00"))
        self.assertEqual(ingreso.material_recuperado, Decimal("50.00"))
        self.assertEqual(ingreso.material_excedente, Decimal("0.00"))
        self.assertEqual(ingreso.pool_material_despues, Decimal("450.00"))
        self.assertEqual(ingreso.monto_total, Decimal("350.00"))
        self.assertEqual(ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(ingreso.comision, Decimal("14.21"))
        self.assertEqual(ingreso.monto_neto, Decimal("335.79"))

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
        self.assertEqual(ingreso.monto_total, Decimal("420.00"))
        self.assertEqual(ingreso.comision, Decimal("17.05"))
        self.assertEqual(ingreso.monto_neto, Decimal("402.95"))

    def test_permite_material_cobrado_si_concepto_permite_material_adicional(self):
        ingreso = self.crear_ingreso(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("50.00"),
        )

        self.assertEqual(ingreso.monto_material_cobrado, Decimal("50.00"))

    def test_no_permite_material_cobrado_si_concepto_no_permite_material_adicional(
        self,
    ):
        with self.assertRaises(ValidationError) as contexto:
            self.crear_ingreso(
                concepto=self.concepto,
                monto_material_cobrado=Decimal("50.00"),
            )

        self.assertEqual(
            contexto.exception.message_dict["monto_material_cobrado"],
            ["Este concepto no permite cobrar material adicional."],
        )

    def test_permite_cero_si_concepto_permite_material_adicional(self):
        ingreso = self.crear_ingreso(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("0.00"),
        )

        self.assertEqual(ingreso.monto_material_cobrado, Decimal("0.00"))
        self.assertEqual(ingreso.material_recuperado, Decimal("0.00"))
        self.assertEqual(ingreso.material_excedente, Decimal("0.00"))


class TicketTests(TestCase):
    def setUp(self):
        self.origen = OrigenIngreso.objects.create(nombre="Consultorio")
        self.concepto = ConceptoIngreso.objects.create(nombre="Consulta")
        self.concepto_material = ConceptoIngreso.objects.create(
            nombre="Curación con material",
            permite_material_adicional=True,
            monto_material_sugerido=Decimal("50.00"),
        )

    def crear_ticket(self, **kwargs):
        datos = {
            "fecha": timezone.now(),
            "estado": Ticket.ESTADO_PENDIENTE,
            "nombre_referencia": "Referencia operativa",
            "origen": self.origen,
        }
        datos.update(kwargs)
        return Ticket.objects.create(**datos)

    def test_ticket_genera_public_id_uuid_unico_y_no_editable(self):
        primero = self.crear_ticket(nombre_referencia="Primero")
        segundo = self.crear_ticket(nombre_referencia="Segundo")

        self.assertIsInstance(primero.public_id, UUID)
        self.assertNotEqual(primero.public_id, segundo.public_id)

        campo = Ticket._meta.get_field("public_id")
        self.assertTrue(campo.unique)
        self.assertFalse(campo.editable)
        self.assertNotIn(
            "public_id",
            modelform_factory(Ticket, fields="__all__").base_fields,
        )
        self.assertIn("public_id", admin.site._registry[Ticket].readonly_fields)

    def test_ticket_pendiente_puede_existir_sin_canal_ni_esquema_comision(self):
        ticket = self.crear_ticket()

        self.assertEqual(ticket.estado, Ticket.ESTADO_PENDIENTE)
        self.assertEqual(ticket.monto_total, Decimal("0.00"))
        self.assertEqual(ticket.monto_material_cobrado, Decimal("0.00"))

    def test_ticket_linea_calcula_monto_total(self):
        ticket = self.crear_ticket()

        linea = TicketLinea.objects.create(
            ticket=ticket,
            concepto=self.concepto,
            cantidad=Decimal("2.00"),
            monto_unitario=Decimal("150.00"),
        )

        self.assertEqual(linea.monto_total, Decimal("300.00"))

    def test_ticket_con_varias_lineas_calcula_monto_total(self):
        ticket = self.crear_ticket()
        TicketLinea.objects.create(
            ticket=ticket,
            concepto=self.concepto,
            cantidad=Decimal("1.00"),
            monto_unitario=Decimal("300.00"),
        )
        TicketLinea.objects.create(
            ticket=ticket,
            concepto=self.concepto_material,
            cantidad=Decimal("2.00"),
            monto_unitario=Decimal("75.00"),
        )

        ticket.refresh_from_db()

        self.assertEqual(ticket.monto_total, Decimal("450.00"))

    def test_ticket_con_lineas_calcula_monto_material_cobrado(self):
        ticket = self.crear_ticket()
        TicketLinea.objects.create(
            ticket=ticket,
            concepto=self.concepto_material,
            cantidad=Decimal("1.00"),
            monto_unitario=Decimal("300.00"),
            monto_material_cobrado=Decimal("50.00"),
        )
        TicketLinea.objects.create(
            ticket=ticket,
            concepto=self.concepto_material,
            cantidad=Decimal("1.00"),
            monto_unitario=Decimal("200.00"),
            monto_material_cobrado=Decimal("25.00"),
        )

        ticket.refresh_from_db()

        self.assertEqual(ticket.monto_material_cobrado, Decimal("75.00"))

    def test_ticket_abandonado_conserva_lineas_y_total(self):
        ticket = self.crear_ticket(estado=Ticket.ESTADO_ABANDONADO)
        TicketLinea.objects.create(
            ticket=ticket,
            concepto=self.concepto,
            cantidad=Decimal("1.00"),
            monto_unitario=Decimal("300.00"),
        )

        ticket.refresh_from_db()

        self.assertEqual(ticket.estado, Ticket.ESTADO_ABANDONADO)
        self.assertEqual(ticket.lineas.count(), 1)
        self.assertEqual(ticket.monto_total, Decimal("300.00"))

    def test_ticket_cobrado_no_crea_ingreso_automaticamente(self):
        ticket = self.crear_ticket(estado=Ticket.ESTADO_COBRADO)
        TicketLinea.objects.create(
            ticket=ticket,
            concepto=self.concepto,
            cantidad=Decimal("1.00"),
            monto_unitario=Decimal("300.00"),
        )

        self.assertEqual(Ingreso.objects.count(), 0)

    def test_ticket_linea_permite_material_si_concepto_permite_material_adicional(self):
        ticket = self.crear_ticket()

        linea = TicketLinea.objects.create(
            ticket=ticket,
            concepto=self.concepto_material,
            cantidad=Decimal("1.00"),
            monto_unitario=Decimal("300.00"),
            monto_material_cobrado=Decimal("50.00"),
        )

        self.assertEqual(linea.monto_material_cobrado, Decimal("50.00"))

    def test_ticket_linea_rechaza_material_si_concepto_no_permite_material_adicional(
        self,
    ):
        ticket = self.crear_ticket()

        with self.assertRaises(ValidationError) as contexto:
            TicketLinea.objects.create(
                ticket=ticket,
                concepto=self.concepto,
                cantidad=Decimal("1.00"),
                monto_unitario=Decimal("300.00"),
                monto_material_cobrado=Decimal("50.00"),
            )

        self.assertEqual(
            contexto.exception.message_dict["monto_material_cobrado"],
            ["Este concepto no permite cobrar material adicional."],
        )

    def test_editar_linea_actualiza_totales_del_ticket(self):
        ticket = self.crear_ticket()
        linea = TicketLinea.objects.create(
            ticket=ticket,
            concepto=self.concepto_material,
            cantidad=Decimal("1.00"),
            monto_unitario=Decimal("300.00"),
            monto_material_cobrado=Decimal("50.00"),
        )

        linea.cantidad = Decimal("2.00")
        linea.monto_unitario = Decimal("200.00")
        linea.monto_material_cobrado = Decimal("75.00")
        linea.save()
        ticket.refresh_from_db()

        self.assertEqual(ticket.monto_total, Decimal("400.00"))
        self.assertEqual(ticket.monto_material_cobrado, Decimal("75.00"))

    def test_eliminar_linea_actualiza_totales_del_ticket(self):
        ticket = self.crear_ticket()
        linea = TicketLinea.objects.create(
            ticket=ticket,
            concepto=self.concepto,
            cantidad=Decimal("1.00"),
            monto_unitario=Decimal("300.00"),
        )
        TicketLinea.objects.create(
            ticket=ticket,
            concepto=self.concepto_material,
            cantidad=Decimal("1.00"),
            monto_unitario=Decimal("200.00"),
            monto_material_cobrado=Decimal("50.00"),
        )

        linea.delete()
        ticket.refresh_from_db()

        self.assertEqual(ticket.monto_total, Decimal("200.00"))
        self.assertEqual(ticket.monto_material_cobrado, Decimal("50.00"))


class TicketPagoTests(TestCase):
    def setUp(self):
        self.metodo_tarjeta = MetodoPago.objects.create(nombre="Tarjeta")
        self.metodo_efectivo = MetodoPago.objects.create(nombre="Efectivo")
        self.canal_tap = CanalCobro.objects.create(
            nombre="Mercado Pago Tap",
            metodo_pago=self.metodo_tarjeta,
        )
        self.canal_caja = CanalCobro.objects.create(
            nombre="Efectivo en caja",
            metodo_pago=self.metodo_efectivo,
        )
        self.esquema_mercado_pago = EsquemaComision.objects.create(
            nombre="Mercado Pago 3.5% + IVA",
            porcentaje_base=Decimal("3.5000"),
            cobra_iva=True,
        )
        self.esquema_mercado_pago.canales_cobro.add(self.canal_tap)
        self.canal_tap.esquema_comision_predeterminado = self.esquema_mercado_pago
        self.canal_tap.save()

        self.esquema_sin_comision = EsquemaComision.objects.create(
            nombre="Sin comisión 0%",
            porcentaje_base=Decimal("0.0000"),
        )
        self.esquema_sin_comision.canales_cobro.add(self.canal_caja)
        self.canal_caja.esquema_comision_predeterminado = self.esquema_sin_comision
        self.canal_caja.save()

        self.esquema_no_asociado = EsquemaComision.objects.create(
            nombre="Esquema no asociado",
            porcentaje_base=Decimal("1.0000"),
        )

        self.concepto_consulta = ConceptoIngreso.objects.create(nombre="Consulta")
        self.concepto_material = ConceptoIngreso.objects.create(
            nombre="Ticket con material",
            permite_material_adicional=True,
            monto_material_sugerido=Decimal("50.00"),
        )
        self.origen = OrigenIngreso.objects.create(nombre="Consultorio")

    def crear_ticket(self, **kwargs):
        datos = {
            "fecha": timezone.datetime(
                2026, 6, 10, 10, 0, tzinfo=timezone.get_current_timezone()
            ),
            "estado": Ticket.ESTADO_PENDIENTE,
            "nombre_referencia": "Referencia de cobro",
            "origen": self.origen,
        }
        datos.update(kwargs)
        return Ticket.objects.create(**datos)

    def agregar_linea(
        self,
        ticket,
        *,
        concepto=None,
        cantidad=Decimal("1.00"),
        monto_unitario=Decimal("300.00"),
        monto_material_cobrado=Decimal("0.00"),
    ):
        return TicketLinea.objects.create(
            ticket=ticket,
            concepto=concepto or self.concepto_consulta,
            cantidad=cantidad,
            monto_unitario=monto_unitario,
            monto_material_cobrado=monto_material_cobrado,
        )

    def cobrar(self, ticket, **kwargs):
        datos = {
            "ticket": ticket,
            "fecha_cobro": timezone.datetime(
                2026, 6, 11, 12, 0, tzinfo=timezone.get_current_timezone()
            ),
            "canal_cobro": self.canal_tap,
            "concepto_ingreso": self.concepto_consulta,
            "notas": "Cobro en caja",
        }
        datos.update(kwargs)
        return cobrar_ticket(**datos)

    def test_ticket_monto_total_cobrado_suma_total_y_material(self):
        ticket = self.crear_ticket()
        self.agregar_linea(
            ticket,
            concepto=self.concepto_material,
            monto_unitario=Decimal("160.00"),
            monto_material_cobrado=Decimal("30.00"),
        )
        ticket.refresh_from_db()

        self.assertEqual(ticket.monto_total, Decimal("160.00"))
        self.assertEqual(ticket.monto_material_cobrado, Decimal("30.00"))
        self.assertEqual(ticket.monto_total_cobrado, Decimal("190.00"))

    def test_cobrar_ticket_pendiente_crea_un_ingreso_y_un_ticket_pago(self):
        ticket = self.crear_ticket()
        self.agregar_linea(ticket)

        pago = self.cobrar(ticket)

        self.assertEqual(Ingreso.objects.count(), 1)
        self.assertEqual(TicketPago.objects.count(), 1)
        self.assertEqual(pago.ticket, ticket)
        self.assertEqual(pago.ingreso, Ingreso.objects.get())

    def test_cobrar_ticket_cambia_estado_a_cobrado(self):
        ticket = self.crear_ticket()
        self.agregar_linea(ticket)

        self.cobrar(ticket)
        ticket.refresh_from_db()

        self.assertEqual(ticket.estado, Ticket.ESTADO_COBRADO)

    def test_ticket_cobrado_no_puede_cobrarse_dos_veces(self):
        ticket = self.crear_ticket()
        self.agregar_linea(ticket)
        self.cobrar(ticket)

        with self.assertRaises(ValidationError):
            self.cobrar(ticket)

        self.assertEqual(Ingreso.objects.count(), 1)
        self.assertEqual(TicketPago.objects.count(), 1)

    def test_ticket_abandonado_no_puede_cobrarse(self):
        ticket = self.crear_ticket(estado=Ticket.ESTADO_ABANDONADO)
        self.agregar_linea(ticket)

        with self.assertRaises(ValidationError):
            self.cobrar(ticket)

        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)

    def test_ticket_cancelado_no_puede_cobrarse(self):
        ticket = self.crear_ticket(estado=Ticket.ESTADO_CANCELADO)
        self.agregar_linea(ticket)

        with self.assertRaises(ValidationError):
            self.cobrar(ticket)

        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)

    def test_ticket_sin_lineas_no_puede_cobrarse(self):
        ticket = self.crear_ticket()

        with self.assertRaises(ValidationError):
            self.cobrar(ticket)

        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)

    def test_ingreso_fecha_usa_fecha_cobro_no_fecha_ticket(self):
        fecha_ticket = timezone.datetime(
            2026, 6, 10, 10, 0, tzinfo=timezone.get_current_timezone()
        )
        fecha_cobro = timezone.datetime(
            2026, 6, 11, 12, 0, tzinfo=timezone.get_current_timezone()
        )
        ticket = self.crear_ticket(fecha=fecha_ticket)
        self.agregar_linea(ticket)

        pago = self.cobrar(ticket, fecha_cobro=fecha_cobro)

        self.assertEqual(pago.ingreso.fecha, fecha_cobro)
        self.assertNotEqual(pago.ingreso.fecha, fecha_ticket)

    def test_ingreso_montos_resumen_salen_del_ticket(self):
        ticket = self.crear_ticket()
        self.agregar_linea(
            ticket,
            concepto=self.concepto_material,
            monto_unitario=Decimal("160.00"),
            monto_material_cobrado=Decimal("30.00"),
        )

        pago = self.cobrar(ticket, concepto_ingreso=self.concepto_material)

        self.assertEqual(pago.ingreso.monto_procedimiento, Decimal("160.00"))
        self.assertEqual(pago.ingreso.monto_material_cobrado, Decimal("30.00"))
        self.assertEqual(pago.ingreso.monto_total, Decimal("190.00"))

    def test_ingreso_calcula_comision_igual_que_ingresos_normales(self):
        ticket = self.crear_ticket()
        self.agregar_linea(
            ticket,
            concepto=self.concepto_material,
            monto_unitario=Decimal("300.00"),
            monto_material_cobrado=Decimal("50.00"),
        )

        pago = self.cobrar(ticket, concepto_ingreso=self.concepto_material)

        self.assertEqual(pago.ingreso.esquema_comision, self.esquema_mercado_pago)
        self.assertEqual(pago.ingreso.porcentaje_comision_aplicado, Decimal("4.0600"))
        self.assertEqual(pago.ingreso.comision, Decimal("14.21"))
        self.assertEqual(pago.ingreso.monto_neto, Decimal("335.79"))

    def test_canal_con_esquema_predeterminado_lo_usa_en_ingreso_y_pago(self):
        ticket = self.crear_ticket()
        self.agregar_linea(ticket)

        pago = self.cobrar(ticket)

        self.assertEqual(pago.ingreso.esquema_comision, self.esquema_mercado_pago)
        self.assertEqual(pago.esquema_comision, self.esquema_mercado_pago)

    def test_esquema_no_asociado_al_canal_hace_fallar_el_cobro(self):
        ticket = self.crear_ticket()
        self.agregar_linea(ticket)

        with self.assertRaises(ValidationError):
            self.cobrar(ticket, esquema_comision=self.esquema_no_asociado)

        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, Ticket.ESTADO_PENDIENTE)
        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)

    def test_material_pool_no_cambia_antes_de_cobrar_y_cambia_al_cobrar(self):
        GastoMaterial.objects.create(
            fecha=timezone.now(),
            monto=Decimal("100.00"),
            descripcion="Material",
        )
        ticket = self.crear_ticket()
        self.agregar_linea(
            ticket,
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("50.00"),
        )

        self.assertEqual(Ingreso.calcular_pool_material_actual(), Decimal("100.00"))

        self.cobrar(ticket, concepto_ingreso=self.concepto_material)

        self.assertEqual(Ingreso.calcular_pool_material_actual(), Decimal("50.00"))

    def test_material_recuperado_y_excedente_se_calculan_como_en_ingresos(self):
        GastoMaterial.objects.create(
            fecha=timezone.now(),
            monto=Decimal("20.00"),
            descripcion="Material",
        )
        ticket = self.crear_ticket()
        self.agregar_linea(
            ticket,
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("50.00"),
        )

        pago = self.cobrar(ticket, concepto_ingreso=self.concepto_material)

        self.assertEqual(pago.ingreso.pool_material_antes, Decimal("20.00"))
        self.assertEqual(pago.ingreso.material_recuperado, Decimal("20.00"))
        self.assertEqual(pago.ingreso.material_excedente, Decimal("30.00"))
        self.assertEqual(pago.ingreso.pool_material_despues, Decimal("0.00"))

    def test_ticket_con_material_requiere_concepto_ingreso_que_permita_material(self):
        ticket = self.crear_ticket()
        self.agregar_linea(
            ticket,
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("50.00"),
        )

        with self.assertRaises(ValidationError) as contexto:
            self.cobrar(ticket, concepto_ingreso=self.concepto_consulta)

        self.assertEqual(
            contexto.exception.message_dict["concepto_ingreso"],
            [
                "El concepto resumen debe permitir material adicional "
                "cuando el ticket tiene material cobrado."
            ],
        )
        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)

    def test_si_falla_creacion_de_ingreso_no_queda_ticket_cobrado(self):
        ticket = self.crear_ticket()
        self.agregar_linea(ticket)

        with self.assertRaises(ValidationError):
            self.cobrar(ticket, esquema_comision=self.esquema_no_asociado)

        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, Ticket.ESTADO_PENDIENTE)
        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)

    def test_ticket_pago_ticket_es_one_to_one(self):
        campo = TicketPago._meta.get_field("ticket")

        self.assertIsInstance(campo, models.OneToOneField)
        self.assertTrue(campo.unique)

    def test_ticket_pago_ingreso_es_one_to_one(self):
        campo = TicketPago._meta.get_field("ingreso")

        self.assertIsInstance(campo, models.OneToOneField)
        self.assertTrue(campo.unique)
