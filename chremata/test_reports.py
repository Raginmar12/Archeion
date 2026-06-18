from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils import timezone

from .models import (
    CajaSesion,
    CanalCobro,
    ConceptoIngreso,
    EsquemaComision,
    GastoMaterial,
    Ingreso,
    MetodoPago,
    OperacionDispositivoChremata,
    OrigenIngreso,
    Ticket,
    TicketLinea,
    TicketPago,
)
from .reports import (
    calcular_reporte_chremata_periodo,
    construir_periodo_anio,
    construir_periodo_dia,
    construir_periodo_mes,
    construir_periodo_semana,
)
from .services import cobrar_ticket


@override_settings(TIME_ZONE="America/Matamoros", USE_TZ=True)
class PeriodoChremataTests(TestCase):
    def setUp(self):
        timezone.activate(ZoneInfo("America/Matamoros"))

    def tearDown(self):
        timezone.deactivate()

    def test_periodo_dia_usa_timezone_local_y_rango_semiabierto(self):
        inicio, fin = construir_periodo_dia(date(2026, 6, 18))

        self.assertTrue(timezone.is_aware(inicio))
        self.assertTrue(timezone.is_aware(fin))
        self.assertEqual(inicio.isoformat(), "2026-06-18T00:00:00-05:00")
        self.assertEqual(fin.isoformat(), "2026-06-19T00:00:00-05:00")

    def test_periodo_semana_usa_semana_iso_lunes_a_lunes(self):
        inicio, fin = construir_periodo_semana(date(2026, 6, 18))

        self.assertEqual(inicio.date(), date(2026, 6, 15))
        self.assertEqual(fin.date(), date(2026, 6, 22))
        self.assertEqual(inicio.weekday(), 0)
        self.assertEqual(fin.weekday(), 0)

    def test_periodo_mes_maneja_cambio_de_anio(self):
        inicio, fin = construir_periodo_mes(2026, 12)

        self.assertEqual(inicio.date(), date(2026, 12, 1))
        self.assertEqual(fin.date(), date(2027, 1, 1))
        self.assertTrue(timezone.is_aware(inicio))
        self.assertTrue(timezone.is_aware(fin))

    def test_periodo_anio_maneja_anio_completo(self):
        inicio, fin = construir_periodo_anio(2026)

        self.assertEqual(inicio.date(), date(2026, 1, 1))
        self.assertEqual(fin.date(), date(2027, 1, 1))
        self.assertTrue(timezone.is_aware(inicio))
        self.assertTrue(timezone.is_aware(fin))


@override_settings(TIME_ZONE="America/Matamoros", USE_TZ=True)
class ReporteChremataPeriodoTests(TestCase):
    def setUp(self):
        timezone.activate(ZoneInfo("America/Matamoros"))
        self.tz = timezone.get_current_timezone()
        self.metodo_efectivo = MetodoPago.objects.create(nombre="Efectivo")
        self.metodo_tarjeta = MetodoPago.objects.create(nombre="Tarjeta")
        self.metodo_transferencia = MetodoPago.objects.create(nombre="Transferencia")
        self.canal_efectivo = CanalCobro.objects.create(
            nombre="Efectivo en caja",
            metodo_pago=self.metodo_efectivo,
        )
        self.canal_tarjeta = CanalCobro.objects.create(
            nombre="Tap (MP)",
            metodo_pago=self.metodo_tarjeta,
        )
        self.canal_transferencia = CanalCobro.objects.create(
            nombre="SPEI",
            metodo_pago=self.metodo_transferencia,
        )
        self.esquema_cero = EsquemaComision.objects.create(
            nombre="Sin comisión",
            porcentaje_base=Decimal("0.0000"),
        )
        self.esquema_diez = EsquemaComision.objects.create(
            nombre="Comisión 10%",
            porcentaje_base=Decimal("10.0000"),
        )
        self.esquema_cero.canales_cobro.add(
            self.canal_efectivo,
            self.canal_transferencia,
        )
        self.esquema_diez.canales_cobro.add(self.canal_tarjeta)
        self.canal_efectivo.esquema_comision_predeterminado = self.esquema_cero
        self.canal_efectivo.save()
        self.canal_transferencia.esquema_comision_predeterminado = self.esquema_cero
        self.canal_transferencia.save()
        self.canal_tarjeta.esquema_comision_predeterminado = self.esquema_diez
        self.canal_tarjeta.save()
        self.concepto_consulta = ConceptoIngreso.objects.create(nombre="Consulta")
        self.concepto_curacion = ConceptoIngreso.objects.create(nombre="Curación")
        self.concepto_resumen = ConceptoIngreso.objects.create(
            nombre="Cobro de ticket",
            permite_material_adicional=True,
        )
        self.concepto_material = ConceptoIngreso.objects.create(
            nombre="Material",
            permite_material_adicional=True,
        )
        self.origen = OrigenIngreso.objects.create(nombre="Consultorio")

    def tearDown(self):
        timezone.deactivate()

    def dt(self, anio, mes, dia, hora=0, minuto=0):
        return datetime(anio, mes, dia, hora, minuto, tzinfo=self.tz)

    def crear_ticket(self, *, fecha=None, estado=Ticket.ESTADO_PENDIENTE):
        return Ticket.objects.create(
            fecha=fecha or self.dt(2026, 6, 18, 9, 0),
            estado=estado,
            origen=self.origen,
            nombre_referencia="Ticket de prueba",
        )

    def agregar_linea(
        self,
        ticket,
        *,
        concepto=None,
        cantidad=Decimal("1.00"),
        monto_unitario=Decimal("100.00"),
        material=Decimal("0.00"),
    ):
        return TicketLinea.objects.create(
            ticket=ticket,
            concepto=concepto or self.concepto_consulta,
            cantidad=cantidad,
            monto_unitario=monto_unitario,
            monto_material_cobrado=material,
        )

    def cobrar(self, *, canal, fecha, lineas, concepto_resumen=None, caja_sesion=None):
        ticket = self.crear_ticket(fecha=fecha)
        for linea in lineas:
            self.agregar_linea(ticket, **linea)
        return cobrar_ticket(
            ticket=ticket,
            fecha_cobro=fecha,
            canal_cobro=canal,
            concepto_ingreso=concepto_resumen or self.concepto_resumen,
            caja_sesion=caja_sesion,
        )

    def calcular_dia(self, dia=18):
        inicio, fin = construir_periodo_dia(date(2026, 6, dia))
        return calcular_reporte_chremata_periodo(inicio, fin, tipo_periodo="dia")

    def test_reporte_diario_basico_usa_ingreso_para_totales_y_agrupa_metodo_canal(self):
        self.cobrar(
            canal=self.canal_efectivo,
            fecha=self.dt(2026, 6, 18, 10, 0),
            lineas=[{"monto_unitario": Decimal("100.00")}],
        )
        self.cobrar(
            canal=self.canal_tarjeta,
            fecha=self.dt(2026, 6, 18, 11, 0),
            lineas=[{"monto_unitario": Decimal("200.00")}],
        )
        self.cobrar(
            canal=self.canal_transferencia,
            fecha=self.dt(2026, 6, 18, 12, 0),
            lineas=[{"monto_unitario": Decimal("300.00")}],
        )
        operacion = OperacionDispositivoChremata.objects.create(
            device_id="zephyros",
            device_entry_id="op-1",
            operation="crear_ticket",
            operation_contract="chremata.operation.crear_ticket.v1",
            payload={},
            payload_hash="hash-1",
            status=OperacionDispositivoChremata.STATUS_PROCESSED,
        )
        OperacionDispositivoChremata.objects.filter(pk=operacion.pk).update(
            recibido_en=self.dt(2026, 6, 18, 8, 0),
        )

        reporte = self.calcular_dia()

        self.assertEqual(reporte["contract"], "chremata.reporte_periodo.v1")
        self.assertEqual(reporte["periodo"]["timezone"], "America/Matamoros")
        self.assertEqual(reporte["totales"]["total_bruto"], "600.00")
        self.assertEqual(reporte["totales"]["total_comisiones"], "20.00")
        self.assertEqual(
            reporte["totales"]["total_neto_despues_comisiones"],
            "580.00",
        )
        self.assertEqual(reporte["totales"]["total_neto_estimado"], "580.00")
        self.assertEqual(reporte["totales"]["total_neto_ganado"], "580.00")
        self.assertEqual(reporte["actividad"]["ingresos"], 3)
        self.assertEqual(reporte["actividad"]["tickets_cobrados"], 3)
        self.assertEqual(reporte["actividad"]["promedio_por_ticket"], "200.00")
        por_metodo = {item["metodo_pago"]: item for item in reporte["por_metodo"]}
        self.assertEqual(por_metodo["Efectivo"]["total_bruto"], "100.00")
        self.assertEqual(por_metodo["Tarjeta"]["total_comisiones"], "20.00")
        self.assertEqual(
            por_metodo["Transferencia"]["total_neto_estimado"],
            "300.00",
        )
        por_canal = {item["canal_cobro"]: item for item in reporte["por_canal"]}
        self.assertEqual(por_canal["Tap (MP)"]["metodo_pago"], "Tarjeta")
        self.assertEqual(reporte["operaciones_dispositivo"]["procesadas"], 1)

    def test_ticket_multilinea_desglosa_por_ticket_linea_no_por_concepto_resumen(self):
        self.cobrar(
            canal=self.canal_efectivo,
            fecha=self.dt(2026, 6, 18, 10, 0),
            lineas=[
                {
                    "concepto": self.concepto_consulta,
                    "monto_unitario": Decimal("100.00"),
                },
                {
                    "concepto": self.concepto_curacion,
                    "monto_unitario": Decimal("250.00"),
                },
            ],
            concepto_resumen=self.concepto_resumen,
        )

        reporte = self.calcular_dia()

        por_concepto = {item["concepto"]: item for item in reporte["por_concepto"]}
        self.assertEqual(set(por_concepto), {"Consulta", "Curación"})
        self.assertEqual(por_concepto["Consulta"]["total"], "100.00")
        self.assertEqual(por_concepto["Curación"]["total"], "250.00")
        self.assertNotIn("Cobro de ticket", por_concepto)

    def test_por_origen_usa_ingreso_no_origen_de_caja(self):
        origen_caja = OrigenIngreso.objects.create(nombre="Similares")
        caja = CajaSesion.objects.create(
            device_id="zephyros",
            origen_ingreso=origen_caja,
            abierta_en=self.dt(2026, 6, 18, 8, 0),
            saldo_inicial_efectivo=Decimal("500.00"),
        )
        self.cobrar(
            canal=self.canal_efectivo,
            fecha=self.dt(2026, 6, 18, 10, 0),
            lineas=[{"monto_unitario": Decimal("100.00")}],
            caja_sesion=caja,
        )

        reporte = self.calcular_dia()

        self.assertEqual(reporte["por_origen"][0]["origen"], "Consultorio")
        self.assertEqual(reporte["por_origen"][0]["total_bruto"], "100.00")
        self.assertEqual(
            reporte["cajas"]["intersectan_periodo"][0]["origen_ingreso"]["nombre"],
            "Similares",
        )

    def test_material_gastos_con_y_sin_caja_y_balance_del_periodo(self):
        caja = CajaSesion.objects.create(
            device_id="zephyros",
            abierta_en=self.dt(2026, 6, 18, 8, 0),
            saldo_inicial_efectivo=Decimal("500.00"),
        )
        GastoMaterial.objects.create(
            fecha=self.dt(2026, 6, 18, 9, 0),
            monto=Decimal("40.00"),
            caja_sesion=caja,
            descripcion="Gasas",
        )
        GastoMaterial.objects.create(
            fecha=self.dt(2026, 6, 18, 13, 0),
            monto=Decimal("15.00"),
            descripcion="Jeringas",
        )
        GastoMaterial.objects.create(
            fecha=self.dt(2026, 6, 17, 13, 0),
            monto=Decimal("99.00"),
            descripcion="Fuera de periodo",
        )
        self.cobrar(
            canal=self.canal_efectivo,
            fecha=self.dt(2026, 6, 18, 10, 0),
            lineas=[
                {
                    "concepto": self.concepto_material,
                    "monto_unitario": Decimal("100.00"),
                    "material": Decimal("25.00"),
                }
            ],
            caja_sesion=caja,
        )

        reporte = self.calcular_dia()

        self.assertEqual(reporte["totales"]["total_material_cobrado"], "25.00")
        self.assertEqual(reporte["totales"]["total_gastos_material"], "55.00")
        self.assertEqual(reporte["totales"]["balance_material_periodo"], "-30.00")
        self.assertEqual(reporte["gastos_material"]["cantidad"], 2)
        self.assertEqual(reporte["gastos_material"]["con_caja"]["total"], "40.00")
        self.assertEqual(reporte["gastos_material"]["sin_caja"]["total"], "15.00")
        self.assertEqual(reporte["gastos_material"]["por_caja"][0]["total"], "40.00")
        self.assertEqual(reporte["por_concepto"][0]["material_cobrado"], "25.00")

    def test_neto_ganado_resta_gastos_material_sin_comisiones(self):
        GastoMaterial.objects.create(
            fecha=self.dt(2026, 6, 18, 9, 0),
            monto=Decimal("99.00"),
            descripcion="Material del día",
        )
        Ingreso.objects.create(
            fecha=self.dt(2026, 6, 18, 10, 0),
            monto_procedimiento=Decimal("925.00"),
            monto_material_cobrado=Decimal("80.00"),
            concepto=self.concepto_material,
            canal_cobro=self.canal_efectivo,
            origen=self.origen,
        )

        reporte = self.calcular_dia()

        self.assertEqual(reporte["totales"]["total_bruto"], "1005.00")
        self.assertEqual(reporte["totales"]["total_comisiones"], "0.00")
        self.assertEqual(
            reporte["totales"]["total_neto_despues_comisiones"],
            "1005.00",
        )
        self.assertEqual(reporte["totales"]["total_neto_estimado"], "1005.00")
        self.assertEqual(reporte["totales"]["total_neto_ganado"], "906.00")
        self.assertEqual(reporte["totales"]["total_ingresos_cobrados"], "1005.00")
        self.assertEqual(reporte["totales"]["total_costo_material"], "99.00")
        self.assertEqual(reporte["totales"]["utilidad_bruta_estimada"], "906.00")
        self.assertEqual(reporte["totales"]["total_comisiones_cobro"], "0.00")
        self.assertEqual(reporte["totales"]["neto_operativo_basico"], "906.00")
        self.assertEqual(reporte["totales"]["balance_material_periodo"], "-19.00")

    def test_neto_ganado_resta_comisiones_y_gastos_material(self):
        GastoMaterial.objects.create(
            fecha=self.dt(2026, 6, 18, 9, 0),
            monto=Decimal("100.00"),
            descripcion="Material del día",
        )
        Ingreso.objects.create(
            fecha=self.dt(2026, 6, 18, 10, 0),
            monto_procedimiento=Decimal("1000.00"),
            concepto=self.concepto_consulta,
            canal_cobro=self.canal_efectivo,
            origen=self.origen,
            comision_manual=True,
            comision=Decimal("35.00"),
        )

        reporte = self.calcular_dia()

        self.assertEqual(reporte["totales"]["total_bruto"], "1000.00")
        self.assertEqual(reporte["totales"]["total_comisiones"], "35.00")
        self.assertEqual(
            reporte["totales"]["total_neto_despues_comisiones"],
            "965.00",
        )
        self.assertEqual(reporte["totales"]["total_neto_estimado"], "965.00")
        self.assertEqual(reporte["totales"]["total_neto_ganado"], "865.00")
        self.assertEqual(reporte["totales"]["total_ingresos_cobrados"], "1000.00")
        self.assertEqual(reporte["totales"]["total_costo_material"], "100.00")
        self.assertEqual(reporte["totales"]["utilidad_bruta_estimada"], "900.00")
        self.assertEqual(reporte["totales"]["total_comisiones_cobro"], "35.00")
        self.assertEqual(reporte["totales"]["neto_operativo_basico"], "865.00")

    def test_limites_inicio_incluyente_fin_excluyente(self):
        inicio, fin = construir_periodo_dia(date(2026, 6, 18))
        self.cobrar(
            canal=self.canal_efectivo,
            fecha=inicio,
            lineas=[{"monto_unitario": Decimal("100.00")}],
        )
        self.cobrar(
            canal=self.canal_efectivo,
            fecha=fin,
            lineas=[{"monto_unitario": Decimal("200.00")}],
        )
        GastoMaterial.objects.create(fecha=inicio, monto=Decimal("10.00"))
        GastoMaterial.objects.create(fecha=fin, monto=Decimal("20.00"))

        reporte = calcular_reporte_chremata_periodo(inicio, fin, tipo_periodo="dia")

        self.assertEqual(reporte["totales"]["total_bruto"], "100.00")
        self.assertEqual(reporte["totales"]["total_gastos_material"], "10.00")
        self.assertEqual(reporte["actividad"]["tickets_cobrados"], 1)

    def test_caja_cruza_medianoche_intersecta_dos_reportes_sin_definir_ingresos(self):
        caja = CajaSesion.objects.create(
            device_id="zephyros",
            origen_ingreso=self.origen,
            estado=CajaSesion.ESTADO_CERRADA,
            abierta_en=self.dt(2026, 6, 18, 23, 30),
            cerrada_en=self.dt(2026, 6, 19, 1, 30),
            saldo_inicial_efectivo=Decimal("100.00"),
            efectivo_contado_cierre=Decimal("200.00"),
        )
        self.cobrar(
            canal=self.canal_efectivo,
            fecha=self.dt(2026, 6, 19, 0, 30),
            lineas=[{"monto_unitario": Decimal("150.00")}],
            caja_sesion=caja,
        )

        reporte_18 = self.calcular_dia(18)
        reporte_19 = self.calcular_dia(19)

        self.assertEqual(reporte_18["cajas"]["cantidad"], 1)
        self.assertEqual(reporte_19["cajas"]["cantidad"], 1)
        self.assertEqual(reporte_18["totales"]["total_bruto"], "0.00")
        self.assertEqual(reporte_19["totales"]["total_bruto"], "150.00")
        self.assertEqual(
            reporte_18["cajas"]["intersectan_periodo"][0]["caja_public_id"],
            str(caja.public_id),
        )
        self.assertIsNone(
            reporte_18["cajas"]["intersectan_periodo"][0]["corte_url"],
        )
        self.assertEqual(
            reporte_18["cajas"]["intersectan_periodo"][0]["origen_ingreso"]["nombre"],
            "Consultorio",
        )

    def test_ticket_pendiente_cuenta_solo_como_actividad(self):
        self.crear_ticket(fecha=self.dt(2026, 6, 18, 14, 0))

        reporte = self.calcular_dia()

        self.assertEqual(reporte["actividad"]["tickets_creados"], 1)
        self.assertEqual(reporte["actividad"]["tickets_pendientes_creados"], 1)
        self.assertEqual(reporte["actividad"]["tickets_cobrados"], 0)
        self.assertEqual(reporte["totales"]["total_bruto"], "0.00")

    def test_ingreso_directo_cuenta_en_totales_y_no_rompe_conceptos_de_ticket(self):
        Ingreso.objects.create(
            fecha=self.dt(2026, 6, 18, 15, 0),
            monto_procedimiento=Decimal("90.00"),
            concepto=self.concepto_consulta,
            canal_cobro=self.canal_efectivo,
            origen=self.origen,
        )

        reporte = self.calcular_dia()

        self.assertEqual(reporte["totales"]["total_bruto"], "90.00")
        self.assertEqual(reporte["actividad"]["ingresos"], 1)
        self.assertEqual(reporte["actividad"]["tickets_cobrados"], 0)
        self.assertEqual(reporte["por_concepto"], [])
        self.assertEqual(
            reporte["ingresos_directos_por_concepto"][0]["total_bruto"],
            "90.00",
        )

    def test_reportes_semana_mes_anio_reutilizan_servicio(self):
        self.cobrar(
            canal=self.canal_efectivo,
            fecha=self.dt(2026, 6, 18, 10, 0),
            lineas=[{"monto_unitario": Decimal("100.00")}],
        )

        for tipo, periodo in (
            ("semana", construir_periodo_semana(date(2026, 6, 18))),
            ("mes", construir_periodo_mes(2026, 6)),
            ("anio", construir_periodo_anio(2026)),
        ):
            with self.subTest(tipo=tipo):
                reporte = calcular_reporte_chremata_periodo(
                    *periodo,
                    tipo_periodo=tipo,
                )
                self.assertEqual(reporte["periodo"]["tipo"], tipo)
                self.assertEqual(reporte["totales"]["total_bruto"], "100.00")

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import resolve, reverse


@override_settings(TIME_ZONE="America/Matamoros", USE_TZ=True)
class ReporteDiarioViewTests(TestCase):
    def setUp(self):
        timezone.activate(ZoneInfo("America/Matamoros"))
        self.user = get_user_model().objects.create_user(
            username="ramiro",
            password="test-password",
        )

    def tearDown(self):
        timezone.deactivate()

    def login(self):
        self.client.force_login(self.user)

    def reporte_fake(self):
        return {
            "contract": "chremata.reporte_periodo.v1",
            "generated_at": "2026-06-18T12:00:00-05:00",
            "periodo": {
                "tipo": "dia",
                "inicio": "2026-06-18T00:00:00-05:00",
                "fin": "2026-06-19T00:00:00-05:00",
                "timezone": "America/Matamoros",
            },
            "totales": {
                "total_bruto": "0.00",
                "total_ingresos_cobrados": "0.00",
                "total_procedimiento": "0.00",
                "total_material_cobrado": "0.00",
                "total_material_recuperado": "0.00",
                "total_material_excedente": "0.00",
                "total_comisiones": "0.00",
                "total_comisiones_cobro": "0.00",
                "total_neto_despues_comisiones": "0.00",
                "total_neto_estimado": "0.00",
                "total_neto_ganado": "0.00",
                "total_gastos_material": "0.00",
                "total_costo_material": "0.00",
                "utilidad_bruta_estimada": "0.00",
                "neto_operativo_basico": "0.00",
                "balance_material_periodo": "0.00",
            },
            "actividad": {
                "tickets_cobrados": 0,
                "ingresos": 0,
                "tickets_creados": 0,
                "tickets_pendientes_creados": 0,
                "tickets_cancelados_creados": 0,
                "tickets_abandonados_creados": 0,
                "promedio_por_ticket": "0.00",
            },
            "por_metodo": [],
            "por_canal": [],
            "por_concepto": [],
            "por_origen": [],
            "ingresos_directos_por_concepto": [],
            "gastos_material": {
                "cantidad": 0,
                "total": "0.00",
                "con_caja": {"cantidad": 0, "total": "0.00"},
                "sin_caja": {"cantidad": 0, "total": "0.00"},
                "por_caja": [],
                "detalle": [],
            },
            "cajas": {
                "cantidad": 0,
                "abiertas": 0,
                "cerradas": 0,
                "intersectan_periodo": [],
            },
            "operaciones_dispositivo": {
                "recibidas": 0,
                "procesadas": 0,
                "fallidas": 0,
                "conflicto": 0,
                "pendientes": 0,
            },
        }


    def test_dashboard_url_name_resuelve(self):
        match = resolve("/chremata/")

        self.assertEqual(match.url_name, "chremata_dashboard")

    def test_dashboard_no_autenticado_redirige_a_login(self):
        response = self.client.get(reverse("chremata_dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])
        self.assertIn("next=/chremata/", response["Location"])

    def test_dashboard_autenticado_carga_sin_datos(self):
        self.login()

        response = self.client.get(reverse("chremata_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "chremata/dashboard.html")
        self.assertContains(response, "Chremata")
        self.assertContains(response, "Sin cajas registradas")
        for texto in ("Ver reporte de hoy", "Ver esta semana", "Ver este mes", "Ver este año"):
            self.assertContains(response, texto)
        self.assertContains(response, reverse("chremata_reporte_diario"))
        self.assertContains(response, reverse("chremata_reporte_semana"))
        self.assertContains(response, reverse("chremata_reporte_mes"))
        self.assertContains(response, reverse("chremata_reporte_anio"))
        self.assertContains(response, "chremata/chremata.css")

    def test_dashboard_muestra_metricas_operativas_visibles(self):
        self.login()

        with patch(
            "chremata.views.calcular_reporte_chremata_periodo",
            return_value=self.reporte_fake(),
        ):
            response = self.client.get(reverse("chremata_dashboard"))

        self.assertEqual(response.status_code, 200)
        for etiqueta in (
            "Ingresos cobrados",
            "Comisiones de cobro",
            "Después de comisiones",
            "Costo de material",
            "Neto operativo básico",
            "Balance material",
        ):
            self.assertContains(response, etiqueta)
        self.assertNotContains(response, "Utilidad bruta estimada")
        self.assertNotContains(response, "Neto " + "ganado")
        self.assertNotContains(response, "Total neto " + "estimado")

    def test_dashboard_usa_reportes_para_hoy_semana_y_mes(self):
        self.login()

        with patch(
            "chremata.views.calcular_reporte_chremata_periodo",
            return_value=self.reporte_fake(),
        ) as calcular_reporte:
            response = self.client.get(reverse("chremata_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calcular_reporte.call_count, 3)
        self.assertEqual(
            [call.kwargs["tipo_periodo"] for call in calcular_reporte.call_args_list],
            ["dia", "semana", "mes"],
        )

    def test_dashboard_muestra_datos_basicos_recientes_y_sin_link_roto_caja(self):
        metodo = MetodoPago.objects.create(nombre="Efectivo")
        canal = CanalCobro.objects.create(nombre="Efectivo en caja", metodo_pago=metodo)
        esquema = EsquemaComision.objects.create(
            nombre="Sin comisión",
            porcentaje_base=Decimal("0.0000"),
        )
        esquema.canales_cobro.add(canal)
        canal.esquema_comision_predeterminado = esquema
        canal.save()
        concepto = ConceptoIngreso.objects.create(nombre="Consulta")
        origen = OrigenIngreso.objects.create(nombre="Consultorio")
        hoy = timezone.localdate()
        fecha = datetime(
            hoy.year,
            hoy.month,
            hoy.day,
            10,
            0,
            tzinfo=timezone.get_current_timezone(),
        )
        caja = CajaSesion.objects.create(
            device_id="zephyros",
            abierta_en=fecha,
            saldo_inicial_efectivo=Decimal("100.00"),
        )
        ingreso = Ingreso.objects.create(
            fecha=fecha,
            monto_procedimiento=Decimal("123.00"),
            concepto=concepto,
            canal_cobro=canal,
            origen=origen,
            caja_sesion=caja,
        )
        ticket = Ticket.objects.create(
            fecha=fecha,
            estado=Ticket.ESTADO_COBRADO,
            nombre_referencia="Cobro reciente",
            origen=origen,
        )
        TicketPago.objects.create(
            ticket=ticket,
            ingreso=ingreso,
            fecha=fecha,
            canal_cobro=canal,
            concepto_ingreso=concepto,
            caja_sesion=caja,
        )
        GastoMaterial.objects.create(
            fecha=fecha,
            monto=Decimal("10.00"),
            descripcion="Gasas",
            caja_sesion=caja,
        )
        self.login()

        response = self.client.get(reverse("chremata_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "$123.00")
        self.assertContains(response, "Cobro reciente")
        self.assertContains(response, "Gasas")
        self.assertContains(response, "Ver caja abierta")
        self.assertContains(response, f"/chremata/cajas/{caja.public_id}/")
        self.assertNotContains(response, 'href="/api/v1/chremata/' + 'cajas/')

    def test_dashboard_muestra_link_a_ultima_caja_si_no_hay_abierta(self):
        caja = CajaSesion.objects.create(
            device_id="zephyros",
            abierta_en=datetime(2026, 6, 18, 8, 0, tzinfo=timezone.get_current_timezone()),
            cerrada_en=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.get_current_timezone()),
            estado=CajaSesion.ESTADO_CERRADA,
            saldo_inicial_efectivo=Decimal("100.00"),
        )
        self.login()

        response = self.client.get(reverse("chremata_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ver última caja")
        self.assertContains(response, f"/chremata/cajas/{caja.public_id}/")
        self.assertNotContains(response, 'href="/api/v1/chremata/' + 'cajas/')

    def test_css_declara_variables_de_identidad_chremata(self):
        css = Path("chremata/static/chremata/chremata.css").read_text()

        self.assertIn("--chremata-bg", css)
        self.assertIn("--chremata-copper", css)
        self.assertIn("--chremata-text", css)

    def test_url_name_resuelve_reporte_diario(self):
        match = resolve("/chremata/reportes/dia/")

        self.assertEqual(match.url_name, "chremata_reporte_diario")

    def test_usuario_no_autenticado_redirige_a_login(self):
        response = self.client.get(reverse("chremata_reporte_diario"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])
        self.assertIn("next=/chremata/reportes/dia/", response["Location"])

    def test_login_template_carga_para_flujo_de_usuario_y_contrasena(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/login.html")
        self.assertContains(response, "Ingresar a Archeion")

    def test_usuario_autenticado_carga_reporte_diario(self):
        self.login()

        response = self.client.get(reverse("chremata_reporte_diario"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "chremata/reportes/dia.html")
        self.assertContains(response, "Reporte diario Chremata")
        self.assertContains(response, "Volver al dashboard")
        self.assertContains(response, "Sin cobros en este periodo.")
        self.assertContains(response, "chremata/chremata.css")

    def test_query_param_fecha_usa_esa_fecha_y_servicio_de_reportes(self):
        self.login()

        with patch(
            "chremata.views.calcular_reporte_chremata_periodo",
            return_value=self.reporte_fake(),
        ) as calcular_reporte:
            response = self.client.get(
                reverse("chremata_reporte_diario"),
                {"fecha": "2026-06-18"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["fecha_consultada"], date(2026, 6, 18))
        calcular_reporte.assert_called_once()
        inicio, fin = calcular_reporte.call_args.args[:2]
        self.assertEqual(inicio.isoformat(), "2026-06-18T00:00:00-05:00")
        self.assertEqual(fin.isoformat(), "2026-06-19T00:00:00-05:00")
        self.assertEqual(calcular_reporte.call_args.kwargs["tipo_periodo"], "dia")

    def test_fecha_invalida_no_rompe_y_muestra_advertencia(self):
        self.login()

        response = self.client.get(
            reverse("chremata_reporte_diario"),
            {"fecha": "no-es-fecha"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "La fecha indicada no tiene formato válido")

    def test_reporte_diario_muestra_navegacion_periodo_con_query_params(self):
        self.login()

        response = self.client.get(reverse("chremata_reporte_diario"), {"fecha": "2026-06-18"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="?fecha=2026-06-17"')
        self.assertContains(response, 'href="?fecha=2026-06-18"')
        self.assertContains(response, 'href="?fecha=2026-06-19"')

    def test_vista_muestra_link_a_detalle_html_de_caja(self):
        origen = OrigenIngreso.objects.create(nombre="Similares")
        CajaSesion.objects.create(
            device_id="zephyros",
            origen_ingreso=origen,
            abierta_en=datetime(
                2026,
                6,
                18,
                8,
                0,
                tzinfo=timezone.get_current_timezone(),
            ),
            saldo_inicial_efectivo=Decimal("100.00"),
        )
        self.login()

        response = self.client.get(
            reverse("chremata_reporte_diario"),
            {"fecha": "2026-06-18"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Origen jornada")
        self.assertContains(response, "Similares")
        self.assertContains(response, "Ver corte")
        self.assertContains(response, "/chremata/cajas/")
        self.assertNotContains(response, 'href="/api/v1/chremata/' + 'cajas/')

    def test_vista_muestra_datos_basicos_del_reporte(self):
        metodo = MetodoPago.objects.create(nombre="Efectivo")
        canal = CanalCobro.objects.create(nombre="Efectivo en caja", metodo_pago=metodo)
        esquema = EsquemaComision.objects.create(
            nombre="Sin comisión",
            porcentaje_base=Decimal("0.0000"),
        )
        esquema.canales_cobro.add(canal)
        canal.esquema_comision_predeterminado = esquema
        canal.save()
        concepto = ConceptoIngreso.objects.create(nombre="Consulta")
        origen = OrigenIngreso.objects.create(nombre="Consultorio")
        Ingreso.objects.create(
            fecha=datetime(2026, 6, 18, 10, 0, tzinfo=timezone.get_current_timezone()),
            monto_procedimiento=Decimal("123.00"),
            concepto=concepto,
            canal_cobro=canal,
            origen=origen,
        )
        self.login()

        response = self.client.get(
            reverse("chremata_reporte_diario"),
            {"fecha": "2026-06-18"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "$123.00")
        self.assertContains(response, "Efectivo")
        self.assertContains(response, "Consultorio")

    def test_reporte_diario_muestra_neto_operativo_basico_y_no_neto_estimado_como_tarjeta(self):
        self.login()

        response = self.client.get(
            reverse("chremata_reporte_diario"),
            {"fecha": "2026-06-18"},
        )

        self.assertEqual(response.status_code, 200)
        for etiqueta in (
            "Ingresos cobrados",
            "Comisiones de cobro",
            "Después de comisiones",
            "Costo de material",
            "Neto operativo básico",
            "Balance material",
        ):
            self.assertContains(response, etiqueta)
        self.assertNotContains(response, "Utilidad bruta estimada")
        self.assertNotContains(response, "Neto " + "ganado")
        self.assertNotContains(response, "Total neto " + "estimado")


    def test_reportes_periodo_url_names_resuelven(self):
        self.assertEqual(resolve("/chremata/reportes/semana/").url_name, "chremata_reporte_semana")
        self.assertEqual(resolve("/chremata/reportes/mes/").url_name, "chremata_reporte_mes")
        self.assertEqual(resolve("/chremata/reportes/anio/").url_name, "chremata_reporte_anio")

    def test_reportes_periodo_no_autenticados_redirigen_a_login(self):
        for name, path in (
            ("chremata_reporte_semana", "/chremata/reportes/semana/"),
            ("chremata_reporte_mes", "/chremata/reportes/mes/"),
            ("chremata_reporte_anio", "/chremata/reportes/anio/"),
        ):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response["Location"])
                self.assertIn(f"next={path}", response["Location"])

    def test_reportes_periodo_autenticados_y_parametros(self):
        self.login()
        casos = (
            ("chremata_reporte_semana", {"fecha": "2026-06-18"}, "semana", "Reporte semanal Chremata"),
            ("chremata_reporte_mes", {"anio": "2026", "mes": "6"}, "mes", "Reporte mensual Chremata"),
            ("chremata_reporte_anio", {"anio": "2026"}, "anio", "Reporte anual Chremata"),
        )
        for name, params, tipo, titulo in casos:
            with self.subTest(name=name):
                with patch("chremata.views.calcular_reporte_chremata_periodo", return_value=self.reporte_fake()) as calcular_reporte:
                    response = self.client.get(reverse(name), params)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "chremata/reportes/periodo.html")
                self.assertContains(response, titulo)
                for etiqueta in (
                    "Ingresos cobrados",
                    "Comisiones de cobro",
                    "Después de comisiones",
                    "Costo de material",
                    "Neto operativo básico",
                    "Balance material",
                ):
                    self.assertContains(response, etiqueta)
                self.assertNotContains(response, "Utilidad bruta estimada")
                self.assertNotContains(response, "Neto " + "ganado")
                self.assertNotContains(response, "Total neto " + "estimado")
                self.assertContains(response, "Sin cobros en este periodo.")
                self.assertContains(response, "Volver al dashboard")
                self.assertContains(response, "chremata/chremata.css")
                self.assertEqual(calcular_reporte.call_args.kwargs["tipo_periodo"], tipo)

    def test_reportes_periodo_muestran_navegacion_con_query_params_correctos(self):
        self.login()
        casos = (
            (
                "chremata_reporte_semana",
                {"fecha": "2026-06-18"},
                ('href="?fecha=2026-06-11"', 'href="?fecha=2026-06-18"', 'href="?fecha=2026-06-25"'),
                ("Semana anterior", "Esta semana", "Semana siguiente"),
            ),
            (
                "chremata_reporte_mes",
                {"anio": "2026", "mes": "6"},
                ('href="?anio=2026&mes=5"', 'href="?anio=2026&mes=6"', 'href="?anio=2026&mes=7"'),
                ("Mes anterior", "Este mes", "Mes siguiente"),
            ),
            (
                "chremata_reporte_anio",
                {"anio": "2026"},
                ('href="?anio=2025"', 'href="?anio=2026"', 'href="?anio=2027"'),
                ("Año anterior", "Este año", "Año siguiente"),
            ),
        )
        for name, params, hrefs, labels in casos:
            with self.subTest(name=name):
                response = self.client.get(reverse(name), params)
                self.assertEqual(response.status_code, 200)
                for href in hrefs:
                    self.assertContains(response, href)
                for label in labels:
                    self.assertContains(response, label)

    def test_reportes_periodo_parametros_invalidos_no_rompen(self):
        self.login()
        for name, params, texto in (
            ("chremata_reporte_semana", {"fecha": "x"}, "La fecha indicada no tiene formato válido"),
            ("chremata_reporte_mes", {"anio": "x", "mes": "99"}, "El mes o año indicado no tiene formato válido"),
            ("chremata_reporte_anio", {"anio": "x"}, "El año indicado no tiene formato válido"),
        ):
            with self.subTest(name=name):
                response = self.client.get(reverse(name), params)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, texto)
                self.assertNotContains(response, "/chremata/cajas/")


    def test_url_name_resuelve_caja_detalle(self):
        caja_id = "12345678-1234-5678-1234-567812345678"
        match = resolve(f"/chremata/cajas/{caja_id}/")

        self.assertEqual(match.url_name, "chremata_caja_detalle")

    def test_caja_detalle_no_autenticado_redirige_a_login(self):
        caja = CajaSesion.objects.create(
            device_id="zephyros",
            abierta_en=datetime(2026, 6, 18, 8, 0, tzinfo=timezone.get_current_timezone()),
            saldo_inicial_efectivo=Decimal("100.00"),
        )

        response = self.client.get(reverse("chremata_caja_detalle", kwargs={"public_id": caja.public_id}))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])
        self.assertIn(f"next=/chremata/cajas/{caja.public_id}/", response["Location"])

    def test_caja_detalle_autenticado_usa_servicio_y_renderiza(self):
        caja = CajaSesion.objects.create(
            device_id="zephyros",
            abierta_en=datetime(2026, 6, 18, 8, 0, tzinfo=timezone.get_current_timezone()),
            cerrada_en=datetime(2026, 6, 18, 14, 0, tzinfo=timezone.get_current_timezone()),
            estado=CajaSesion.ESTADO_CERRADA,
            saldo_inicial_efectivo=Decimal("100.00"),
            efectivo_contado_cierre=Decimal("250.00"),
            notas_apertura="Inicio de consulta",
            notas_cierre="Cierre normal",
        )
        corte = self.reporte_fake()
        corte.update({
            "contract": "chremata.corte_caja.v1",
            "caja": {
                "caja_public_id": str(caja.public_id),
                "estado": "cerrada",
                "device_id": "zephyros",
                "caja_fisica": None,
                "origen_ingreso": {
                    "public_id": "12345678-1234-5678-1234-567812345678",
                    "nombre": "Similares",
                },
                "abierta_en": "2026-06-18T13:00:00Z",
                "cerrada_en": "2026-06-18T19:00:00Z",
            },
            "efectivo": {
                "saldo_inicial_efectivo": "100.00",
                "total_efectivo": "200.00",
                "efectivo_esperado": "250.00",
                "efectivo_contado_cierre": "250.00",
                "diferencia_efectivo": "0.00",
            },
            "totales": {
                "total_bruto": "300.00",
                "total_efectivo": "200.00",
                "total_tarjeta": "100.00",
                "total_transferencia": "0.00",
                "total_material_cobrado": "50.00",
                "total_comisiones": "5.00",
                "total_neto_estimado": "295.00",
            },
            "totales_por_metodo": [{"metodo_pago": "Efectivo", "cantidad": 1, "total_bruto": "200.00", "total_comisiones": "0.00", "total_neto_estimado": "200.00"}],
            "totales_por_canal": [{"canal_cobro": "Efectivo en caja", "metodo_pago": "Efectivo", "cantidad": 1, "total_bruto": "200.00", "total_comisiones": "0.00", "total_neto_estimado": "200.00"}],
            "totales_por_concepto": [{"concepto": "Consulta", "cantidad_total": "1.00", "lineas": 1, "total": "300.00", "material_cobrado": "50.00"}],
            "gastos_material": {"cantidad": 1, "total_gastos_material": "50.00", "detalle": [{"fecha": "2026-06-18T15:00:00Z", "monto": "50.00", "descripcion": "Gasas", "notas": "Caja"}]},
            "tickets": {"tickets_cobrados": 1, "tickets_pendientes_creados_durante_caja": 0, "tickets_cancelados_creados_durante_caja": 0, "tickets_abandonados_creados_durante_caja": 0},
        })
        self.login()

        with patch("chremata.views.calcular_corte_caja", return_value=corte) as calcular_corte:
            response = self.client.get(reverse("chremata_caja_detalle", kwargs={"public_id": caja.public_id}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "chremata/cajas/detalle.html")
        calcular_corte.assert_called_once_with(caja)
        self.assertContains(response, "Corte de caja")
        self.assertContains(response, "zephyros")
        self.assertContains(response, "cerrada")
        self.assertContains(response, "Origen de jornada")
        self.assertContains(response, "Similares")
        self.assertContains(response, "Inicio de consulta")
        self.assertContains(response, "Cierre normal")
        self.assertContains(response, "$100.00")
        self.assertContains(response, "$250.00")
        self.assertContains(response, "Gasas")
        self.assertContains(response, "Consulta")
        self.assertContains(response, "Efectivo en caja")
        self.assertContains(response, "Tickets cobrados")
        self.assertContains(response, "Volver al dashboard")
        self.assertContains(response, "Ver reporte diario")
        self.assertContains(response, "Volver")
        self.assertContains(response, "difference-ok")
        self.assertNotContains(response, 'href="/api/v1/chremata/' + 'cajas/')

    def test_caja_detalle_inexistente_devuelve_404(self):
        self.login()

        response = self.client.get(reverse("chremata_caja_detalle", kwargs={"public_id": "12345678-1234-5678-1234-567812345678"}))

        self.assertEqual(response.status_code, 404)

    def test_caja_detalle_abierta_sin_datos_carga_sin_romper(self):
        caja = CajaSesion.objects.create(
            device_id="zephyros",
            abierta_en=datetime(2026, 6, 18, 8, 0, tzinfo=timezone.get_current_timezone()),
            saldo_inicial_efectivo=Decimal("100.00"),
        )
        self.login()

        response = self.client.get(reverse("chremata_caja_detalle", kwargs={"public_id": caja.public_id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Caja abierta / cierre pendiente")
        self.assertContains(response, "Sin origen de jornada")
        self.assertContains(response, "Sin notas registradas.")
        self.assertNotContains(response, 'href="/api/v1/chremata/' + 'cajas/')
