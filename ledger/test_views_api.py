import json
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import DeviceToken

from .models import (
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


@override_settings(DEBUG=False, CODEX_DEVICE_TOKEN="")
class CatalogosApiTests(TestCase):
    def setUp(self):
        self.device_token, self.token_completo = DeviceToken.crear("Cardputer")
        self.url = reverse("api-v1-catalogos")

        self.metodo = MetodoPago.objects.create(nombre="Tarjeta")
        self.metodo_inactivo = MetodoPago.objects.create(
            nombre="Efectivo inactivo",
            activo=False,
        )
        self.canal = CanalCobro.objects.create(
            nombre="Mercado Pago Tap",
            metodo_pago=self.metodo,
        )
        self.canal_sin_esquema = CanalCobro.objects.create(
            nombre="Terminal sin esquema",
            metodo_pago=self.metodo,
        )
        self.canal_inactivo = CanalCobro.objects.create(
            nombre="Canal inactivo",
            metodo_pago=self.metodo,
            activo=False,
        )
        self.esquema = EsquemaComision.objects.create(
            nombre="Mercado Pago 3.5% + IVA",
            porcentaje_base=Decimal("3.5000"),
            cobra_iva=True,
        )
        self.esquema.canales_cobro.add(self.canal, self.canal_inactivo)
        self.canal.esquema_comision_predeterminado = self.esquema
        self.canal.save()
        self.esquema_inactivo = EsquemaComision.objects.create(
            nombre="Esquema inactivo",
            porcentaje_base=Decimal("1.0000"),
            activo=False,
        )
        self.concepto = ConceptoIngreso.objects.create(
            nombre="Consulta con material",
            descripcion="Consulta general",
            permite_material_adicional=True,
            monto_material_sugerido=Decimal("50.00"),
        )
        self.concepto_inactivo = ConceptoIngreso.objects.create(
            nombre="Concepto inactivo",
            activo=False,
        )
        self.origen = OrigenIngreso.objects.create(
            nombre="Consultorio",
            descripcion="Consultorio principal",
        )
        self.origen_sin_descripcion = OrigenIngreso.objects.create(
            nombre="Mostrador sin descripción",
        )
        self.origen_inactivo = OrigenIngreso.objects.create(
            nombre="Origen inactivo",
            activo=False,
        )

    def get_catalogos(self):
        return self.client.get(
            self.url,
            headers={"X-Codex-Device-Token": self.token_completo},
        )

    def test_responde_200_con_token_valido(self):
        response = self.get_catalogos()

        self.assertEqual(response.status_code, 200)

    def test_responde_401_sin_token_cuando_hay_device_token_activo(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)

    @patch("ledger.views_api.timezone")
    def test_devuelve_metadatos_y_catalogos(self, timezone_mock):
        timezone_mock.now.return_value = datetime(
            2026,
            6,
            4,
            23,
            10,
            0,
            987654,
            tzinfo=datetime_timezone.utc,
        )

        data = self.get_catalogos().json()

        timezone_mock.now.assert_called_once_with()
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["contract"], "chremata.catalogs.v1")
        self.assertEqual(data["app"], "chremata")
        self.assertEqual(data["generated_at"], "2026-06-04T23:10:00Z")
        self.assertEqual(data["snapshot_id"], "cat_2026-06-04T23:10:00Z")
        self.assertEqual(
            set(data["catalogs"]),
            {
                "metodos_pago",
                "canales_cobro",
                "esquemas_comision",
                "conceptos_ingreso",
                "origenes_ingreso",
            },
        )

    def test_devuelve_catalogos_activos_y_excluye_inactivos(self):
        catalogs = self.get_catalogos().json()["catalogs"]

        self.assertEqual(
            {item["nombre"] for item in catalogs["metodos_pago"]},
            {self.metodo.nombre},
        )
        self.assertEqual(
            {item["nombre"] for item in catalogs["canales_cobro"]},
            {self.canal.nombre, self.canal_sin_esquema.nombre},
        )
        self.assertEqual(
            {item["nombre"] for item in catalogs["esquemas_comision"]},
            {self.esquema.nombre},
        )
        self.assertEqual(
            {item["nombre"] for item in catalogs["conceptos_ingreso"]},
            {self.concepto.nombre},
        )
        self.assertEqual(
            {item["nombre"] for item in catalogs["origenes_ingreso"]},
            {self.origen.nombre, self.origen_sin_descripcion.nombre},
        )

    def test_catalogos_y_canales_de_esquemas_tienen_orden_estable(self):
        metodo_alfabetico = MetodoPago.objects.create(nombre="A método")
        canal_alfabetico = CanalCobro.objects.create(
            nombre="A canal",
            metodo_pago=metodo_alfabetico,
        )
        esquema_alfabetico = EsquemaComision.objects.create(
            nombre="A esquema",
            porcentaje_base=Decimal("0.0000"),
        )
        concepto_alfabetico = ConceptoIngreso.objects.create(nombre="A concepto")
        origen_alfabetico = OrigenIngreso.objects.create(nombre="A origen")
        self.esquema.canales_cobro.add(canal_alfabetico, self.canal_sin_esquema)

        catalogs = self.get_catalogos().json()["catalogs"]

        self.assertEqual(
            [item["id"] for item in catalogs["metodos_pago"]],
            [metodo_alfabetico.id, self.metodo.id],
        )
        self.assertEqual(
            [item["id"] for item in catalogs["canales_cobro"]],
            [canal_alfabetico.id, self.canal.id, self.canal_sin_esquema.id],
        )
        self.assertEqual(
            [item["id"] for item in catalogs["esquemas_comision"]],
            [esquema_alfabetico.id, self.esquema.id],
        )
        self.assertEqual(
            [item["id"] for item in catalogs["conceptos_ingreso"]],
            [concepto_alfabetico.id, self.concepto.id],
        )
        self.assertEqual(
            [item["id"] for item in catalogs["origenes_ingreso"]],
            [
                origen_alfabetico.id,
                self.origen.id,
                self.origen_sin_descripcion.id,
            ],
        )
        esquema = next(
            item
            for item in catalogs["esquemas_comision"]
            if item["id"] == self.esquema.id
        )
        self.assertEqual(
            esquema["canales_cobro_ids"],
            [canal_alfabetico.id, self.canal.id, self.canal_sin_esquema.id],
        )
        self.assertEqual(
            esquema["canales_cobro_public_ids"],
            [
                str(canal_alfabetico.public_id),
                str(self.canal.public_id),
                str(self.canal_sin_esquema.public_id),
            ],
        )

    def test_todos_los_catalogos_incluyen_public_id_como_string(self):
        catalogs = self.get_catalogos().json()["catalogs"]

        for nombre_catalogo, items in catalogs.items():
            with self.subTest(catalogo=nombre_catalogo):
                for item in items:
                    self.assertIsInstance(item["public_id"], str)
                    UUID(item["public_id"])

    def test_canales_incluyen_datos_del_metodo_pago(self):
        canales = self.get_catalogos().json()["catalogs"]["canales_cobro"]
        canal = next(item for item in canales if item["id"] == self.canal.id)

        self.assertEqual(canal["metodo_pago_id"], self.metodo.id)
        self.assertEqual(canal["metodo_pago_public_id"], str(self.metodo.public_id))
        self.assertEqual(canal["metodo_pago"], self.metodo.nombre)

    def test_canales_incluyen_esquema_predeterminado_o_null(self):
        canales = self.get_catalogos().json()["catalogs"]["canales_cobro"]
        canal = next(item for item in canales if item["id"] == self.canal.id)
        canal_sin_esquema = next(
            item for item in canales if item["id"] == self.canal_sin_esquema.id
        )

        self.assertEqual(
            canal["esquema_comision_predeterminado_id"],
            self.esquema.id,
        )
        self.assertEqual(
            canal["esquema_comision_predeterminado_public_id"],
            str(self.esquema.public_id),
        )
        self.assertIsNone(canal_sin_esquema["esquema_comision_predeterminado_id"])
        self.assertIsNone(
            canal_sin_esquema["esquema_comision_predeterminado_public_id"],
        )

    def test_esquemas_incluyen_porcentaje_total_y_canales_activos(self):
        esquemas = self.get_catalogos().json()["catalogs"]["esquemas_comision"]
        esquema = esquemas[0]

        self.assertEqual(esquema["porcentaje_total"], "4.0600")
        self.assertEqual(esquema["canales_cobro_ids"], [self.canal.id])
        self.assertEqual(
            esquema["canales_cobro_public_ids"],
            [str(self.canal.public_id)],
        )

    def test_conceptos_incluyen_campos_de_material(self):
        conceptos = self.get_catalogos().json()["catalogs"]["conceptos_ingreso"]
        concepto = conceptos[0]

        self.assertTrue(concepto["permite_material_adicional"])
        self.assertEqual(concepto["monto_material_sugerido"], "50.00")

    def test_origenes_incluyen_descripcion_como_string(self):
        origenes = self.get_catalogos().json()["catalogs"]["origenes_ingreso"]
        origen = next(item for item in origenes if item["id"] == self.origen.id)
        origen_sin_descripcion = next(
            item for item in origenes if item["id"] == self.origen_sin_descripcion.id
        )

        self.assertIsInstance(origen["descripcion"], str)
        self.assertEqual(origen["descripcion"], "Consultorio principal")
        self.assertIsInstance(origen_sin_descripcion["descripcion"], str)
        self.assertEqual(origen_sin_descripcion["descripcion"], "")

    def test_decimales_se_devuelven_como_strings(self):
        catalogs = self.get_catalogos().json()["catalogs"]
        esquema = catalogs["esquemas_comision"][0]
        concepto = catalogs["conceptos_ingreso"][0]

        self.assertIsInstance(esquema["porcentaje_base"], str)
        self.assertIsInstance(esquema["porcentaje_iva"], str)
        self.assertIsInstance(esquema["porcentaje_total"], str)
        self.assertIsInstance(concepto["monto_material_sugerido"], str)


@override_settings(DEBUG=False, CODEX_DEVICE_TOKEN="")
class ChremataOperationsApiTests(TestCase):
    def setUp(self):
        self.device_token, self.token_completo = DeviceToken.crear("Zephyros")
        self.url = reverse("api-v1-chremata-operations")
        self.origen = OrigenIngreso.objects.create(nombre="Consultorio")
        self.metodo_tarjeta = MetodoPago.objects.create(nombre="Tarjeta")
        self.canal_tap = CanalCobro.objects.create(
            nombre="Mercado Pago Tap",
            metodo_pago=self.metodo_tarjeta,
        )
        self.esquema_mercado_pago = EsquemaComision.objects.create(
            nombre="Mercado Pago 3.5% + IVA",
            porcentaje_base=Decimal("3.5000"),
            cobra_iva=True,
        )
        self.esquema_mercado_pago.canales_cobro.add(self.canal_tap)
        self.canal_tap.esquema_comision_predeterminado = self.esquema_mercado_pago
        self.canal_tap.save()
        self.esquema_no_asociado = EsquemaComision.objects.create(
            nombre="Esquema no asociado",
            porcentaje_base=Decimal("1.0000"),
        )
        self.concepto = ConceptoIngreso.objects.create(nombre="Consulta")
        self.concepto_material = ConceptoIngreso.objects.create(
            nombre="Curación con material",
            permite_material_adicional=True,
        )

    def post_operation(self, payload, token=None):
        headers = {}
        if token is not None:
            headers["X-Codex-Device-Token"] = token
        else:
            headers["X-Codex-Device-Token"] = self.token_completo
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            headers=headers,
        )

    def crear_ticket_para_cobrar(
        self,
        *,
        estado=Ticket.ESTADO_PENDIENTE,
        concepto=None,
        monto_unitario=Decimal("160.00"),
        monto_material_cobrado=Decimal("0.00"),
        crear_linea=True,
    ):
        ticket = Ticket.objects.create(
            fecha=datetime(2026, 6, 10, 10, tzinfo=datetime_timezone.utc),
            estado=estado,
            nombre_referencia="Referencia de cobro",
            origen=self.origen,
        )
        if crear_linea:
            TicketLinea.objects.create(
                ticket=ticket,
                concepto=concepto or self.concepto,
                cantidad=Decimal("1.00"),
                monto_unitario=monto_unitario,
                monto_material_cobrado=monto_material_cobrado,
            )
        ticket.refresh_from_db()
        return ticket

    def payload_cobrar_ticket(self, ticket, **overrides):
        payload = {
            "operation": "cobrar_ticket",
            "operation_contract": "chremata.operation.cobrar_ticket.v1",
            "device_id": "zephyros-cardputer",
            "device_entry_id": str(uuid4()),
            "ticket_public_id": str(ticket.public_id),
            "fecha_cobro": "2026-06-11T12:00:00Z",
            "canal_cobro_public_id": str(self.canal_tap.public_id),
            "esquema_comision_public_id": None,
            "concepto_ingreso_resumen_public_id": str(self.concepto.public_id),
            "notas": "Cobro offline",
        }
        payload.update(overrides)
        return payload

    def payload_cancelar_ticket(self, ticket, **overrides):
        payload = {
            "operation": "cancelar_ticket",
            "operation_contract": "chremata.operation.cancelar_ticket.v1",
            "device_id": "zephyros-cardputer",
            "device_entry_id": str(uuid4()),
            "ticket_public_id": str(ticket.public_id),
            "fecha_cancelacion": "2026-06-11T12:00:00Z",
            "notas": "Cancelación offline",
        }
        payload.update(overrides)
        return payload

    def payload_abandonar_ticket(self, ticket, **overrides):
        payload = {
            "operation": "abandonar_ticket",
            "operation_contract": "chremata.operation.abandonar_ticket.v1",
            "device_id": "zephyros-cardputer",
            "device_entry_id": str(uuid4()),
            "ticket_public_id": str(ticket.public_id),
            "fecha_abandono": "2026-06-11T12:00:00Z",
            "notas": "Abandono offline",
        }
        payload.update(overrides)
        return payload

    def payload_crear_ticket(self, **overrides):
        ticket = {
            "ticket_public_id": str(uuid4()),
            "fecha": "2026-06-10T10:00:00Z",
            "estado": "pendiente",
            "nombre_referencia": "Referencia operativa",
            "origen_ingreso_public_id": str(self.origen.public_id),
            "notas": "Ticket offline",
            "lineas": [
                {
                    "concepto_ingreso_public_id": str(self.concepto.public_id),
                    "descripcion": "Consulta",
                    "cantidad": "2.00",
                    "monto_unitario": "80.00",
                    "monto_total": "160.00",
                    "monto_material_cobrado": "0.00",
                    "orden": 1,
                    "notas": "",
                },
            ],
        }
        payload = {
            "operation": "crear_ticket",
            "operation_contract": "chremata.operation.crear_ticket.v1",
            "device_id": "zephyros-cardputer",
            "device_entry_id": str(uuid4()),
            "ticket": ticket,
        }
        for key, value in overrides.items():
            if key == "ticket":
                payload["ticket"].update(value)
            else:
                payload[key] = value
        return payload

    def test_post_con_token_valido_funciona(self):
        response = self.post_operation(self.payload_crear_ticket())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_post_sin_token_responde_401(self):
        response = self.client.post(
            self.url,
            data=json.dumps(self.payload_crear_ticket()),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_post_con_token_invalido_responde_401(self):
        response = self.post_operation(self.payload_crear_ticket(), token="incorrecto")

        self.assertEqual(response.status_code, 401)

    def test_crear_ticket_exitoso_crea_ticket_y_linea(self):
        payload = self.payload_crear_ticket()

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(TicketLinea.objects.count(), 1)
        ticket = Ticket.objects.get()
        self.assertEqual(str(ticket.public_id), payload["ticket"]["ticket_public_id"])
        self.assertEqual(ticket.estado, Ticket.ESTADO_PENDIENTE)
        self.assertEqual(ticket.lineas.get().monto_total, Decimal("160.00"))

    def test_crear_ticket_no_crea_ingreso_ni_ticket_pago(self):
        self.post_operation(self.payload_crear_ticket())

        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)

    def test_respuesta_exitosa_no_expone_ids_internos_y_montos_son_strings(self):
        response = self.post_operation(self.payload_crear_ticket()).json()

        self.assertNotIn("id", response["result"])
        self.assertNotIn("ticket_id", response["result"])
        self.assertEqual(response["result"]["monto_total"], "160.00")
        self.assertEqual(response["result"]["monto_material_cobrado"], "0.00")
        self.assertEqual(response["result"]["monto_total_cobrado"], "160.00")

    def test_crear_ticket_con_material_calcula_totales(self):
        payload = self.payload_crear_ticket(
            ticket={
                "lineas": [
                    {
                        "concepto_ingreso_public_id": str(
                            self.concepto_material.public_id
                        ),
                        "descripcion": "Curación",
                        "cantidad": "1.00",
                        "monto_unitario": "160.00",
                        "monto_total": "160.00",
                        "monto_material_cobrado": "30.00",
                        "orden": 1,
                        "notas": "",
                    },
                ],
            },
        )

        data = self.post_operation(payload).json()

        self.assertEqual(data["result"]["monto_total"], "160.00")
        self.assertEqual(data["result"]["monto_material_cobrado"], "30.00")
        self.assertEqual(data["result"]["monto_total_cobrado"], "190.00")

    def test_reenviar_misma_operacion_devuelve_duplicate_y_no_duplica_ticket(self):
        payload = self.payload_crear_ticket()
        primera = self.post_operation(payload)
        segunda = self.post_operation(payload)

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertFalse(primera.json()["duplicate"])
        self.assertTrue(segunda.json()["duplicate"])
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(TicketLinea.objects.count(), 1)

    def test_reenviar_misma_llave_con_payload_distinto_devuelve_409(self):
        payload = self.payload_crear_ticket()
        self.post_operation(payload)
        payload_distinto = self.payload_crear_ticket(
            device_entry_id=payload["device_entry_id"],
            ticket={"nombre_referencia": "Otra referencia"},
        )

        response = self.post_operation(payload_distinto)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "payload_conflict")
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(Ticket.objects.get().nombre_referencia, "Referencia operativa")

    def test_json_invalido_devuelve_400(self):
        response = self.client.post(
            self.url,
            data="{no-json",
            content_type="application/json",
            headers={"X-Codex-Device-Token": self.token_completo},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_json")

    def test_falta_device_entry_id_devuelve_400(self):
        payload = self.payload_crear_ticket()
        del payload["device_entry_id"]

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["fields"]["device_entry_id"], "required"
        )

    def test_operation_desconocida_devuelve_400_y_se_registra_failed(self):
        payload = self.payload_crear_ticket(operation="crear_gasto_material")

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "unsupported_operation")
        self.assertEqual(
            OperacionDispositivoChremata.objects.get().status,
            OperacionDispositivoChremata.STATUS_FAILED,
        )

    def test_operation_contract_incorrecto_devuelve_400(self):
        payload = self.payload_crear_ticket(operation_contract="contrato.incorrecto")

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_operation_contract")

    def test_origen_inexistente_devuelve_422(self):
        payload = self.payload_crear_ticket(
            ticket={"origen_ingreso_public_id": str(uuid4())},
        )

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "reference_not_found")
        self.assertEqual(response.json()["error"]["field"], "origen_ingreso_public_id")

    def test_concepto_inexistente_devuelve_422(self):
        payload = self.payload_crear_ticket(
            ticket={
                "lineas": [
                    {
                        "concepto_ingreso_public_id": str(uuid4()),
                        "descripcion": "Consulta",
                        "cantidad": "1.00",
                        "monto_unitario": "80.00",
                        "monto_total": "80.00",
                        "monto_material_cobrado": "0.00",
                        "orden": 1,
                        "notas": "",
                    },
                ],
            },
        )

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "reference_not_found")

    def test_ticket_public_id_repetido_por_otra_operacion_falla(self):
        ticket_public_id = uuid4()
        Ticket.objects.create(
            public_id=ticket_public_id,
            fecha=datetime(2026, 6, 10, 10, tzinfo=datetime_timezone.utc),
            estado=Ticket.ESTADO_PENDIENTE,
            origen=self.origen,
        )
        payload = self.payload_crear_ticket(
            ticket={"ticket_public_id": str(ticket_public_id)},
        )

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "ticket_public_id_conflict")
        self.assertEqual(Ticket.objects.count(), 1)

    def test_estado_distinto_de_pendiente_falla(self):
        payload = self.payload_crear_ticket(ticket={"estado": "cobrado"})

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["error"]["fields"]["estado"],
            ["crear_ticket solo acepta estado pendiente."],
        )
        self.assertEqual(Ticket.objects.count(), 0)

    def test_lineas_vacias_falla(self):
        payload = self.payload_crear_ticket(ticket={"lineas": []})

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["fields"]["lineas"], "required_non_empty_list"
        )

    def test_monto_total_inconsistente_falla(self):
        payload = self.payload_crear_ticket(
            ticket={
                "lineas": [
                    {
                        "concepto_ingreso_public_id": str(self.concepto.public_id),
                        "descripcion": "Consulta",
                        "cantidad": "2.00",
                        "monto_unitario": "80.00",
                        "monto_total": "100.00",
                        "monto_material_cobrado": "0.00",
                        "orden": 1,
                        "notas": "",
                    },
                ],
            },
        )

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "line_total_mismatch")
        self.assertEqual(Ticket.objects.count(), 0)

    def test_material_invalido_falla_si_concepto_no_permite_material(self):
        payload = self.payload_crear_ticket(
            ticket={
                "lineas": [
                    {
                        "concepto_ingreso_public_id": str(self.concepto.public_id),
                        "descripcion": "Consulta",
                        "cantidad": "1.00",
                        "monto_unitario": "80.00",
                        "monto_total": "80.00",
                        "monto_material_cobrado": "10.00",
                        "orden": 1,
                        "notas": "",
                    },
                ],
            },
        )

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "business_validation_error")
        self.assertEqual(Ticket.objects.count(), 0)

    def test_rollback_si_una_linea_falla_no_deja_ticket_parcial(self):
        payload = self.payload_crear_ticket(
            ticket={
                "lineas": [
                    {
                        "concepto_ingreso_public_id": str(
                            self.concepto_material.public_id
                        ),
                        "descripcion": "Curación",
                        "cantidad": "1.00",
                        "monto_unitario": "80.00",
                        "monto_total": "80.00",
                        "monto_material_cobrado": "10.00",
                        "orden": 1,
                        "notas": "",
                    },
                    {
                        "concepto_ingreso_public_id": str(self.concepto.public_id),
                        "descripcion": "Consulta",
                        "cantidad": "1.00",
                        "monto_unitario": "80.00",
                        "monto_total": "70.00",
                        "monto_material_cobrado": "0.00",
                        "orden": 2,
                        "notas": "",
                    },
                ],
            },
        )

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(Ticket.objects.count(), 0)
        self.assertEqual(TicketLinea.objects.count(), 0)
        self.assertEqual(
            OperacionDispositivoChremata.objects.get().status,
            OperacionDispositivoChremata.STATUS_FAILED,
        )

    def test_reenvio_de_operacion_fallida_devuelve_mismo_error(self):
        payload = self.payload_crear_ticket(ticket={"lineas": []})

        primera = self.post_operation(payload)
        segunda = self.post_operation(payload)

        self.assertEqual(primera.status_code, 400)
        self.assertEqual(segunda.status_code, 422)
        self.assertTrue(segunda.json()["duplicate"])
        self.assertEqual(
            segunda.json()["error"],
            primera.json()["error"],
        )
        self.assertEqual(OperacionDispositivoChremata.objects.count(), 1)

    def test_cobrar_ticket_con_token_valido_funciona(self):
        ticket = self.crear_ticket_para_cobrar()

        response = self.post_operation(self.payload_cobrar_ticket(ticket))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_cobrar_ticket_sin_token_responde_401(self):
        ticket = self.crear_ticket_para_cobrar()

        response = self.client.post(
            self.url,
            data=json.dumps(self.payload_cobrar_ticket(ticket)),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_cobrar_ticket_pendiente_crea_pago_ingreso_y_cambia_estado(self):
        ticket = self.crear_ticket_para_cobrar()

        response = self.post_operation(self.payload_cobrar_ticket(ticket))

        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, Ticket.ESTADO_COBRADO)
        self.assertEqual(TicketPago.objects.count(), 1)
        self.assertEqual(Ingreso.objects.count(), 1)
        operacion = OperacionDispositivoChremata.objects.get()
        self.assertEqual(
            operacion.status, OperacionDispositivoChremata.STATUS_PROCESSED
        )
        self.assertEqual(operacion.ticket, ticket)
        self.assertEqual(operacion.ingreso, Ingreso.objects.get())
        self.assertEqual(operacion.ticket_pago, TicketPago.objects.get())

    def test_cobrar_ticket_respuesta_publica_incluye_snapshots_sin_ids_internos(self):
        GastoMaterial.objects.create(
            fecha=datetime(2026, 6, 10, 8, tzinfo=datetime_timezone.utc),
            monto=Decimal("350.00"),
            descripcion="Material",
        )
        ticket = self.crear_ticket_para_cobrar(
            concepto=self.concepto_material,
            monto_unitario=Decimal("160.00"),
            monto_material_cobrado=Decimal("30.00"),
        )
        payload = self.payload_cobrar_ticket(
            ticket,
            concepto_ingreso_resumen_public_id=str(self.concepto_material.public_id),
        )

        data = self.post_operation(payload).json()
        result = data["result"]

        self.assertNotIn("id", result)
        self.assertNotIn("ingreso_id", result)
        self.assertNotIn("ticket_pago_id", result)
        self.assertEqual(result["ticket_public_id"], str(ticket.public_id))
        self.assertEqual(result["ticket_estado"], Ticket.ESTADO_COBRADO)
        self.assertEqual(result["fecha_cobro"], "2026-06-11T12:00:00Z")
        self.assertEqual(result["monto_total"], "160.00")
        self.assertEqual(result["monto_material_cobrado"], "30.00")
        self.assertEqual(result["monto_total_cobrado"], "190.00")
        self.assertEqual(result["porcentaje_comision_aplicado"], "4.0600")
        self.assertEqual(result["comision"], "7.71")
        self.assertEqual(result["monto_neto"], "182.29")
        self.assertEqual(result["material_recuperado"], "30.00")
        self.assertEqual(result["material_excedente"], "0.00")
        self.assertEqual(result["pool_material_antes"], "350.00")
        self.assertEqual(result["pool_material_despues"], "320.00")

    def test_reenviar_mismo_cobrar_ticket_no_duplica_ingreso_ni_pago(self):
        ticket = self.crear_ticket_para_cobrar()
        payload = self.payload_cobrar_ticket(ticket)

        primera = self.post_operation(payload)
        segunda = self.post_operation(payload)

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertFalse(primera.json()["duplicate"])
        self.assertTrue(segunda.json()["duplicate"])
        self.assertEqual(Ingreso.objects.count(), 1)
        self.assertEqual(TicketPago.objects.count(), 1)

    def test_reenviar_cobrar_ticket_misma_llave_payload_distinto_devuelve_409(self):
        ticket = self.crear_ticket_para_cobrar()
        payload = self.payload_cobrar_ticket(ticket)
        self.post_operation(payload)
        payload_distinto = self.payload_cobrar_ticket(
            ticket,
            device_entry_id=payload["device_entry_id"],
            notas="Otra nota",
        )

        response = self.post_operation(payload_distinto)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "payload_conflict")
        self.assertEqual(Ingreso.objects.count(), 1)
        self.assertEqual(TicketPago.objects.count(), 1)

    def test_cobrar_ticket_referencias_inexistentes_devuelven_422(self):
        casos = [
            ("ticket_public_id", str(uuid4())),
            ("canal_cobro_public_id", str(uuid4())),
            ("esquema_comision_public_id", str(uuid4())),
            ("concepto_ingreso_resumen_public_id", str(uuid4())),
        ]
        for campo, valor in casos:
            with self.subTest(campo=campo):
                ticket = self.crear_ticket_para_cobrar()
                payload = self.payload_cobrar_ticket(ticket, **{campo: valor})

                response = self.post_operation(payload)

                self.assertEqual(response.status_code, 422)
                self.assertEqual(
                    response.json()["error"]["code"], "reference_not_found"
                )

    def test_cobrar_ticket_estados_no_pendientes_fallan(self):
        for estado in [
            Ticket.ESTADO_COBRADO,
            Ticket.ESTADO_CANCELADO,
            Ticket.ESTADO_ABANDONADO,
        ]:
            with self.subTest(estado=estado):
                ticket = self.crear_ticket_para_cobrar(estado=estado)
                payload = self.payload_cobrar_ticket(ticket)

                response = self.post_operation(payload)

                self.assertEqual(response.status_code, 422)
                self.assertEqual(
                    response.json()["error"]["code"], "business_validation_error"
                )
                self.assertEqual(Ingreso.objects.count(), 0)
                self.assertEqual(TicketPago.objects.count(), 0)

    def test_cobrar_ticket_sin_lineas_falla(self):
        ticket = self.crear_ticket_para_cobrar(crear_linea=False)

        response = self.post_operation(self.payload_cobrar_ticket(ticket))

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "business_validation_error")
        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)

    def test_cobrar_ticket_con_material_requiere_concepto_resumen_material(self):
        ticket = self.crear_ticket_para_cobrar(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("30.00"),
        )

        response = self.post_operation(self.payload_cobrar_ticket(ticket))

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "business_validation_error")
        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)

    def test_cobrar_ticket_esquema_no_asociado_falla_y_hace_rollback(self):
        ticket = self.crear_ticket_para_cobrar()
        payload = self.payload_cobrar_ticket(
            ticket,
            esquema_comision_public_id=str(self.esquema_no_asociado.public_id),
        )

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "business_validation_error")
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, Ticket.ESTADO_PENDIENTE)
        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)
        self.assertEqual(
            OperacionDispositivoChremata.objects.get().status,
            OperacionDispositivoChremata.STATUS_FAILED,
        )

    def test_reenvio_cobrar_ticket_fallido_devuelve_error_guardado(self):
        ticket = self.crear_ticket_para_cobrar(crear_linea=False)
        payload = self.payload_cobrar_ticket(ticket)

        primera = self.post_operation(payload)
        segunda = self.post_operation(payload)

        self.assertEqual(primera.status_code, 422)
        self.assertEqual(segunda.status_code, 422)
        self.assertTrue(segunda.json()["duplicate"])
        self.assertEqual(segunda.json()["error"], primera.json()["error"])
        self.assertEqual(OperacionDispositivoChremata.objects.count(), 1)

    def test_cobrar_ticket_afecta_pool_material_mediante_ingreso(self):
        GastoMaterial.objects.create(
            fecha=datetime(2026, 6, 10, 8, tzinfo=datetime_timezone.utc),
            monto=Decimal("100.00"),
            descripcion="Material",
        )
        ticket = self.crear_ticket_para_cobrar(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("50.00"),
        )
        self.assertEqual(Ingreso.calcular_pool_material_actual(), Decimal("100.00"))

        response = self.post_operation(
            self.payload_cobrar_ticket(
                ticket,
                concepto_ingreso_resumen_public_id=str(
                    self.concepto_material.public_id
                ),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Ingreso.calcular_pool_material_actual(), Decimal("50.00"))
        result = response.json()["result"]
        self.assertEqual(result["material_recuperado"], "50.00")
        self.assertEqual(result["material_excedente"], "0.00")
        self.assertEqual(result["pool_material_antes"], "100.00")
        self.assertEqual(result["pool_material_despues"], "50.00")

    def test_cobrar_ticket_ingreso_fecha_usa_fecha_cobro_no_fecha_ticket(self):
        ticket = self.crear_ticket_para_cobrar()

        response = self.post_operation(self.payload_cobrar_ticket(ticket))

        self.assertEqual(response.status_code, 200)
        ingreso = Ingreso.objects.get()
        self.assertEqual(
            ingreso.fecha,
            datetime(2026, 6, 11, 12, tzinfo=datetime_timezone.utc),
        )
        self.assertNotEqual(ingreso.fecha, ticket.fecha)

    def test_cancelar_ticket_con_token_valido_funciona(self):
        ticket = self.crear_ticket_para_cobrar()

        response = self.post_operation(self.payload_cancelar_ticket(ticket))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_cancelar_ticket_sin_token_responde_401(self):
        ticket = self.crear_ticket_para_cobrar()

        response = self.client.post(
            self.url,
            data=json.dumps(self.payload_cancelar_ticket(ticket)),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_cancelar_ticket_cambia_estado_y_no_crea_registros_oficiales(self):
        ticket = self.crear_ticket_para_cobrar(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("30.00"),
        )
        monto_total = ticket.monto_total
        monto_material = ticket.monto_material_cobrado

        response = self.post_operation(self.payload_cancelar_ticket(ticket))

        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, Ticket.ESTADO_CANCELADO)
        self.assertEqual(ticket.lineas.count(), 1)
        self.assertEqual(ticket.monto_total, monto_total)
        self.assertEqual(ticket.monto_material_cobrado, monto_material)
        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)
        operacion = OperacionDispositivoChremata.objects.get()
        self.assertEqual(
            operacion.status, OperacionDispositivoChremata.STATUS_PROCESSED
        )
        self.assertEqual(operacion.ticket, ticket)
        self.assertIsNone(operacion.ingreso)
        self.assertIsNone(operacion.ticket_pago)

    def test_cancelar_ticket_respuesta_publica(self):
        ticket = self.crear_ticket_para_cobrar(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("30.00"),
        )

        data = self.post_operation(self.payload_cancelar_ticket(ticket)).json()
        result = data["result"]

        self.assertNotIn("id", result)
        self.assertNotIn("ingreso_id", result)
        self.assertNotIn("ticket_pago_id", result)
        self.assertEqual(result["ticket_public_id"], str(ticket.public_id))
        self.assertEqual(result["ticket_estado"], Ticket.ESTADO_CANCELADO)
        self.assertEqual(result["fecha_cancelacion"], "2026-06-11T12:00:00Z")
        self.assertEqual(result["monto_total"], "160.00")
        self.assertEqual(result["monto_material_cobrado"], "30.00")
        self.assertEqual(result["monto_total_cobrado"], "190.00")

    def test_reenviar_cancelar_ticket_mismo_payload_es_idempotente(self):
        ticket = self.crear_ticket_para_cobrar()
        payload = self.payload_cancelar_ticket(ticket)

        primera = self.post_operation(payload)
        segunda = self.post_operation(payload)

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertFalse(primera.json()["duplicate"])
        self.assertTrue(segunda.json()["duplicate"])
        self.assertEqual(Ticket.objects.get().estado, Ticket.ESTADO_CANCELADO)
        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)

    def test_cancelar_ticket_misma_llave_payload_distinto_devuelve_409(self):
        ticket = self.crear_ticket_para_cobrar()
        payload = self.payload_cancelar_ticket(ticket)
        self.post_operation(payload)
        payload_distinto = self.payload_cancelar_ticket(
            ticket,
            device_entry_id=payload["device_entry_id"],
            notas="Otra nota",
        )

        response = self.post_operation(payload_distinto)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "payload_conflict")

    def test_cancelar_ticket_referencia_inexistente_devuelve_422(self):
        ticket = self.crear_ticket_para_cobrar()
        payload = self.payload_cancelar_ticket(ticket, ticket_public_id=str(uuid4()))

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "reference_not_found")

    def test_cancelar_ticket_estados_no_pendientes_fallan(self):
        for estado in [
            Ticket.ESTADO_COBRADO,
            Ticket.ESTADO_ABANDONADO,
            Ticket.ESTADO_CANCELADO,
        ]:
            with self.subTest(estado=estado):
                ticket = self.crear_ticket_para_cobrar(estado=estado)
                payload = self.payload_cancelar_ticket(ticket)

                response = self.post_operation(payload)

                self.assertEqual(response.status_code, 422)
                self.assertEqual(
                    response.json()["error"]["code"], "business_validation_error"
                )
                self.assertEqual(Ingreso.objects.count(), 0)
                self.assertEqual(TicketPago.objects.count(), 0)

    def test_cancelar_ticket_fallido_queda_guardado_y_reenvio_devuelve_error(self):
        ticket = self.crear_ticket_para_cobrar(estado=Ticket.ESTADO_CANCELADO)
        payload = self.payload_cancelar_ticket(ticket)

        primera = self.post_operation(payload)
        segunda = self.post_operation(payload)

        self.assertEqual(primera.status_code, 422)
        self.assertEqual(segunda.status_code, 422)
        self.assertTrue(segunda.json()["duplicate"])
        self.assertEqual(segunda.json()["error"], primera.json()["error"])
        self.assertEqual(
            OperacionDispositivoChremata.objects.get().status,
            OperacionDispositivoChremata.STATUS_FAILED,
        )

    def test_abandonar_ticket_con_token_valido_funciona(self):
        ticket = self.crear_ticket_para_cobrar()

        response = self.post_operation(self.payload_abandonar_ticket(ticket))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_abandonar_ticket_sin_token_responde_401(self):
        ticket = self.crear_ticket_para_cobrar()

        response = self.client.post(
            self.url,
            data=json.dumps(self.payload_abandonar_ticket(ticket)),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_abandonar_ticket_cambia_estado_y_conserva_datos_sin_registros_oficiales(
        self,
    ):
        ticket = self.crear_ticket_para_cobrar(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("30.00"),
        )
        nombre_referencia = ticket.nombre_referencia
        monto_total = ticket.monto_total
        monto_material = ticket.monto_material_cobrado

        response = self.post_operation(self.payload_abandonar_ticket(ticket))

        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, Ticket.ESTADO_ABANDONADO)
        self.assertEqual(ticket.nombre_referencia, nombre_referencia)
        self.assertEqual(ticket.lineas.count(), 1)
        self.assertEqual(ticket.monto_total, monto_total)
        self.assertEqual(ticket.monto_material_cobrado, monto_material)
        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)
        operacion = OperacionDispositivoChremata.objects.get()
        self.assertEqual(operacion.ticket, ticket)
        self.assertIsNone(operacion.ingreso)
        self.assertIsNone(operacion.ticket_pago)

    def test_abandonar_ticket_respuesta_publica(self):
        ticket = self.crear_ticket_para_cobrar(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("30.00"),
        )

        data = self.post_operation(self.payload_abandonar_ticket(ticket)).json()
        result = data["result"]

        self.assertNotIn("id", result)
        self.assertNotIn("ingreso_id", result)
        self.assertNotIn("ticket_pago_id", result)
        self.assertEqual(result["ticket_public_id"], str(ticket.public_id))
        self.assertEqual(result["ticket_estado"], Ticket.ESTADO_ABANDONADO)
        self.assertEqual(result["fecha_abandono"], "2026-06-11T12:00:00Z")
        self.assertEqual(result["nombre_referencia"], "Referencia de cobro")
        self.assertEqual(result["monto_total"], "160.00")
        self.assertEqual(result["monto_material_cobrado"], "30.00")
        self.assertEqual(result["monto_total_cobrado"], "190.00")

    def test_reenviar_abandonar_ticket_mismo_payload_es_idempotente(self):
        ticket = self.crear_ticket_para_cobrar()
        payload = self.payload_abandonar_ticket(ticket)

        primera = self.post_operation(payload)
        segunda = self.post_operation(payload)

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertFalse(primera.json()["duplicate"])
        self.assertTrue(segunda.json()["duplicate"])
        self.assertEqual(Ticket.objects.get().estado, Ticket.ESTADO_ABANDONADO)
        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)

    def test_abandonar_ticket_misma_llave_payload_distinto_devuelve_409(self):
        ticket = self.crear_ticket_para_cobrar()
        payload = self.payload_abandonar_ticket(ticket)
        self.post_operation(payload)
        payload_distinto = self.payload_abandonar_ticket(
            ticket,
            device_entry_id=payload["device_entry_id"],
            notas="Otra nota",
        )

        response = self.post_operation(payload_distinto)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "payload_conflict")

    def test_abandonar_ticket_referencia_inexistente_devuelve_422(self):
        ticket = self.crear_ticket_para_cobrar()
        payload = self.payload_abandonar_ticket(ticket, ticket_public_id=str(uuid4()))

        response = self.post_operation(payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "reference_not_found")

    def test_abandonar_ticket_estados_no_pendientes_fallan(self):
        for estado in [
            Ticket.ESTADO_COBRADO,
            Ticket.ESTADO_CANCELADO,
            Ticket.ESTADO_ABANDONADO,
        ]:
            with self.subTest(estado=estado):
                ticket = self.crear_ticket_para_cobrar(estado=estado)
                payload = self.payload_abandonar_ticket(ticket)

                response = self.post_operation(payload)

                self.assertEqual(response.status_code, 422)
                self.assertEqual(
                    response.json()["error"]["code"], "business_validation_error"
                )
                self.assertEqual(Ingreso.objects.count(), 0)
                self.assertEqual(TicketPago.objects.count(), 0)

    def test_abandonar_ticket_fallido_queda_guardado_y_reenvio_devuelve_error(self):
        ticket = self.crear_ticket_para_cobrar(estado=Ticket.ESTADO_ABANDONADO)
        payload = self.payload_abandonar_ticket(ticket)

        primera = self.post_operation(payload)
        segunda = self.post_operation(payload)

        self.assertEqual(primera.status_code, 422)
        self.assertEqual(segunda.status_code, 422)
        self.assertTrue(segunda.json()["duplicate"])
        self.assertEqual(segunda.json()["error"], primera.json()["error"])
        self.assertEqual(
            OperacionDispositivoChremata.objects.get().status,
            OperacionDispositivoChremata.STATUS_FAILED,
        )

    def test_cancelar_y_abandonar_ticket_no_cambian_material_pool(self):
        GastoMaterial.objects.create(
            fecha=datetime(2026, 6, 10, 8, tzinfo=datetime_timezone.utc),
            monto=Decimal("100.00"),
            descripcion="Material",
        )
        ticket_cancelar = self.crear_ticket_para_cobrar(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("50.00"),
        )
        ticket_abandonar = self.crear_ticket_para_cobrar(
            concepto=self.concepto_material,
            monto_material_cobrado=Decimal("30.00"),
        )

        self.post_operation(self.payload_cancelar_ticket(ticket_cancelar))
        self.post_operation(self.payload_abandonar_ticket(ticket_abandonar))

        self.assertEqual(Ingreso.calcular_pool_material_actual(), Decimal("100.00"))
        self.assertEqual(Ingreso.objects.count(), 0)
        self.assertEqual(TicketPago.objects.count(), 0)


@override_settings(DEBUG=False, CODEX_DEVICE_TOKEN="")
class MaterialPoolApiTests(TestCase):
    def setUp(self):
        self.device_token, self.token_completo = DeviceToken.crear("Zephyros")
        self.url = reverse("api-v1-chremata-material-pool")

        self.metodo = MetodoPago.objects.create(nombre="Tarjeta")
        self.canal = CanalCobro.objects.create(
            nombre="Mercado Pago Tap",
            metodo_pago=self.metodo,
        )
        self.esquema = EsquemaComision.objects.create(
            nombre="Mercado Pago 3.5% + IVA",
            porcentaje_base=Decimal("3.5000"),
            cobra_iva=True,
        )
        self.esquema.canales_cobro.add(self.canal)
        self.canal.esquema_comision_predeterminado = self.esquema
        self.canal.save()
        self.concepto = ConceptoIngreso.objects.create(
            nombre="Consulta con material",
            permite_material_adicional=True,
        )
        self.origen = OrigenIngreso.objects.create(nombre="Consultorio")

    def get_material_pool(self):
        return self.client.get(
            self.url,
            headers={"X-Codex-Device-Token": self.token_completo},
        )

    def crear_gasto(self, monto, fecha):
        return GastoMaterial.objects.create(
            fecha=fecha,
            monto=monto,
            descripcion="Material",
        )

    def crear_ingreso_con_material(
        self,
        monto_material_cobrado,
        fecha,
        monto_procedimiento=Decimal("100.00"),
    ):
        return Ingreso.objects.create(
            fecha=fecha,
            monto_procedimiento=monto_procedimiento,
            monto_material_cobrado=monto_material_cobrado,
            concepto=self.concepto,
            canal_cobro=self.canal,
            origen=self.origen,
        )

    def test_responde_200_con_token_valido(self):
        response = self.get_material_pool()

        self.assertEqual(response.status_code, 200)

    def test_responde_401_sin_token_cuando_hay_device_token_activo(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)

    @patch("ledger.views_api.timezone")
    def test_respuesta_incluye_metadata_y_campos_requeridos(self, timezone_mock):
        timezone_mock.now.return_value = datetime(
            2026,
            6,
            8,
            4,
            12,
            0,
            123456,
            tzinfo=datetime_timezone.utc,
        )

        data = self.get_material_pool().json()

        self.assertEqual(data["contract"], "chremata.material_pool.v1")
        self.assertEqual(data["app"], "chremata")
        self.assertEqual(data["server_role"], "archeion")
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["generated_at"], "2026-06-08T04:12:00Z")
        self.assertIn("pool_material_actual", data)
        self.assertIn("total_gastos_material", data)
        self.assertIn("total_material_recuperado", data)
        self.assertIn("ultimo_gasto_material_fecha", data)
        self.assertIn("ultimo_ingreso_con_material_fecha", data)

    def test_sin_gastos_ni_ingresos_devuelve_ceros_y_fechas_null(self):
        data = self.get_material_pool().json()

        self.assertEqual(data["total_gastos_material"], "0.00")
        self.assertEqual(data["total_material_recuperado"], "0.00")
        self.assertEqual(data["pool_material_actual"], "0.00")
        self.assertIsNone(data["ultimo_gasto_material_fecha"])
        self.assertIsNone(data["ultimo_ingreso_con_material_fecha"])

    def test_total_gastos_material_refleja_suma_de_gastos(self):
        self.crear_gasto(
            Decimal("500.00"),
            datetime(2026, 6, 7, 20, 10, tzinfo=datetime_timezone.utc),
        )
        self.crear_gasto(
            Decimal("700.00"),
            datetime(2026, 6, 8, 20, 10, tzinfo=datetime_timezone.utc),
        )

        data = self.get_material_pool().json()

        self.assertEqual(data["total_gastos_material"], "1200.00")
        self.assertEqual(data["pool_material_actual"], "1200.00")

    def test_ingresos_con_material_actualizan_recuperado_y_pool(self):
        self.crear_gasto(
            Decimal("1200.00"),
            datetime(2026, 6, 7, 20, 10, tzinfo=datetime_timezone.utc),
        )
        self.crear_ingreso_con_material(
            Decimal("850.00"),
            datetime(2026, 6, 7, 22, 40, tzinfo=datetime_timezone.utc),
        )

        data = self.get_material_pool().json()

        self.assertEqual(data["total_material_recuperado"], "850.00")
        self.assertEqual(data["pool_material_actual"], "350.00")

    def test_pool_material_actual_nunca_baja_de_cero(self):
        self.crear_gasto(
            Decimal("10.00"),
            datetime(2026, 6, 7, 20, 10, tzinfo=datetime_timezone.utc),
        )
        ingreso = self.crear_ingreso_con_material(
            Decimal("10.00"),
            datetime(2026, 6, 7, 22, 40, tzinfo=datetime_timezone.utc),
        )
        Ingreso.objects.filter(pk=ingreso.pk).update(
            material_recuperado=Decimal("30.00"),
        )

        data = self.get_material_pool().json()

        self.assertEqual(data["total_gastos_material"], "10.00")
        self.assertEqual(data["total_material_recuperado"], "30.00")
        self.assertEqual(data["pool_material_actual"], "0.00")

    def test_montos_se_devuelven_como_strings_decimales_con_dos_decimales(self):
        self.crear_gasto(
            Decimal("1.50"),
            datetime(2026, 6, 7, 20, 10, tzinfo=datetime_timezone.utc),
        )

        data = self.get_material_pool().json()

        self.assertIsInstance(data["total_gastos_material"], str)
        self.assertIsInstance(data["total_material_recuperado"], str)
        self.assertIsInstance(data["pool_material_actual"], str)
        self.assertEqual(data["total_gastos_material"], "1.50")
        self.assertEqual(data["total_material_recuperado"], "0.00")
        self.assertEqual(data["pool_material_actual"], "1.50")

    @patch("ledger.views_api.timezone")
    def test_generated_at_no_tiene_microsegundos_y_usa_z(self, timezone_mock):
        timezone_mock.now.return_value = datetime(
            2026,
            6,
            8,
            4,
            12,
            0,
            999999,
            tzinfo=datetime_timezone.utc,
        )

        data = self.get_material_pool().json()

        self.assertEqual(data["generated_at"], "2026-06-08T04:12:00Z")
        self.assertNotIn(".", data["generated_at"])
        self.assertTrue(data["generated_at"].endswith("Z"))

    def test_ultimo_gasto_material_fecha_usa_gasto_mas_reciente(self):
        self.crear_gasto(
            Decimal("100.00"),
            datetime(2026, 6, 6, 20, 10, 1, 123456, tzinfo=datetime_timezone.utc),
        )
        self.crear_gasto(
            Decimal("200.00"),
            datetime(2026, 6, 7, 20, 10, 2, 654321, tzinfo=datetime_timezone.utc),
        )

        data = self.get_material_pool().json()

        self.assertEqual(
            data["ultimo_gasto_material_fecha"],
            "2026-06-07T20:10:02Z",
        )

    def test_ultimo_ingreso_con_material_fecha_usa_ingreso_con_material_mas_reciente(
        self,
    ):
        self.crear_gasto(
            Decimal("500.00"),
            datetime(2026, 6, 6, 20, 10, tzinfo=datetime_timezone.utc),
        )
        self.crear_ingreso_con_material(
            Decimal("50.00"),
            datetime(2026, 6, 7, 22, 40, 1, 123456, tzinfo=datetime_timezone.utc),
        )
        self.crear_ingreso_con_material(
            Decimal("0.00"),
            datetime(2026, 6, 8, 22, 40, 2, tzinfo=datetime_timezone.utc),
        )
        self.crear_ingreso_con_material(
            Decimal("25.00"),
            datetime(2026, 6, 9, 22, 40, 3, 654321, tzinfo=datetime_timezone.utc),
        )

        data = self.get_material_pool().json()

        self.assertEqual(
            data["ultimo_ingreso_con_material_fecha"],
            "2026-06-09T22:40:03Z",
        )


@override_settings(DEBUG=False, CODEX_DEVICE_TOKEN="")
class ChremataSchemaApiTests(TestCase):
    def setUp(self):
        self.device_token, self.token_completo = DeviceToken.crear("Zephyros")
        self.url = reverse("api-v1-chremata-schema")

    def get_schema(self):
        return self.client.get(
            self.url,
            headers={"X-Codex-Device-Token": self.token_completo},
        )

    def catalog_field_names(self, data, catalog_name):
        return {field["name"] for field in data["catalogs"][catalog_name]["fields"]}

    def operation_payload_field_names(self, data, operation_name):
        return {
            field["name"]
            for field in data["operations"][operation_name]["payload_fields"]
        }

    def ticket_entity_field_names(self, data, entity_name):
        return {
            field["name"]
            for field in data["tickets"]["entities"][entity_name]["fields"]
        }

    def operation_payload_fields_by_name(self, data, operation_name):
        return {
            field["name"]: field
            for field in data["operations"][operation_name]["payload_fields"]
        }

    def test_responde_200_con_token_valido(self):
        response = self.get_schema()

        self.assertEqual(response.status_code, 200)

    def test_responde_401_sin_token_cuando_hay_device_token_activo(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)

    @patch("ledger.views_api.timezone")
    def test_incluye_metadata_y_secciones_principales(self, timezone_mock):
        timezone_mock.now.return_value = datetime(
            2026,
            6,
            6,
            0,
            0,
            0,
            123456,
            tzinfo=datetime_timezone.utc,
        )

        data = self.get_schema().json()

        timezone_mock.now.assert_called_once_with()
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["contract"], "chremata.schema.v1")
        self.assertEqual(data["app"], "chremata")
        self.assertEqual(data["server_role"], "archeion")
        self.assertEqual(data["generated_at"], "2026-06-06T00:00:00Z")
        self.assertEqual(
            data["compatible_with"],
            {
                "catalogs": ["chremata.catalogs.v1"],
                "operations": [
                    "chremata.operation.crear_ingreso.v1",
                    "chremata.operation.crear_gasto_material.v1",
                    "chremata.operation.crear_ticket.v1",
                    "chremata.operation.cobrar_ticket.v1",
                    "chremata.operation.cancelar_ticket.v1",
                    "chremata.operation.abandonar_ticket.v1",
                ],
                "clients": ["zephyros"],
            },
        )
        self.assertIn("catalog_snapshot", data)
        self.assertIn("catalogs", data)
        self.assertIn("operations", data)

    def test_catalog_snapshot_describe_endpoint_de_catalogos(self):
        snapshot = self.get_schema().json()["catalog_snapshot"]

        self.assertEqual(snapshot["endpoint"], "/api/v1/catalogos/")
        self.assertEqual(snapshot["contract"], "chremata.catalogs.v1")
        self.assertEqual(snapshot["current_schema_version"], 1)
        self.assertEqual(snapshot["identity_field"], "public_id")
        self.assertTrue(snapshot["contains_only_active_records"])
        self.assertTrue(snapshot["decimals_are_strings"])
        self.assertTrue(snapshot["uuids_are_strings"])
        self.assertTrue(snapshot["nullable_fields_use_null"])

    def test_declara_material_pool(self):
        material_pool = self.get_schema().json()["material_pool"]

        self.assertEqual(material_pool["endpoint"], "/api/v1/chremata/material-pool/")
        self.assertEqual(material_pool["contract"], "chremata.material_pool.v1")
        self.assertEqual(material_pool["schema_version"], 1)
        self.assertEqual(
            set(material_pool["fields"]),
            {
                "contract",
                "app",
                "server_role",
                "schema_version",
                "generated_at",
                "pool_material_actual",
                "total_gastos_material",
                "total_material_recuperado",
                "ultimo_gasto_material_fecha",
                "ultimo_ingreso_con_material_fecha",
            },
        )
        self.assertEqual(
            material_pool["fields"]["generated_at"],
            {"type": "datetime_utc_string", "required": True},
        )
        self.assertEqual(
            material_pool["fields"]["pool_material_actual"],
            {"type": "decimal_string", "required": True},
        )
        self.assertEqual(
            material_pool["fields"]["total_gastos_material"],
            {"type": "decimal_string", "required": True},
        )
        self.assertEqual(
            material_pool["fields"]["total_material_recuperado"],
            {"type": "decimal_string", "required": True},
        )
        self.assertEqual(
            material_pool["fields"]["ultimo_gasto_material_fecha"],
            {
                "type": "datetime_utc_string",
                "required": False,
                "nullable": True,
            },
        )
        self.assertEqual(
            material_pool["fields"]["ultimo_ingreso_con_material_fecha"],
            {
                "type": "datetime_utc_string",
                "required": False,
                "nullable": True,
            },
        )

    def test_declara_contratos_de_tickets(self):
        tickets = self.get_schema().json()["tickets"]

        self.assertEqual(
            set(tickets["entities"]),
            {"ticket", "ticket_linea", "ticket_pago"},
        )
        self.assertEqual(
            tickets["entities"]["ticket"]["contract"],
            "chremata.ticket.v1",
        )
        self.assertEqual(
            tickets["entities"]["ticket_linea"]["contract"],
            "chremata.ticket_line.v1",
        )
        self.assertEqual(
            tickets["entities"]["ticket_pago"]["contract"],
            "chremata.ticket_payment.v1",
        )
        self.assertEqual(
            tickets["entities"]["ticket"]["allowed_states"],
            ["pendiente", "cobrado", "cancelado", "abandonado"],
        )

    def test_declara_campos_de_ticket_y_linea(self):
        data = self.get_schema().json()

        self.assertEqual(
            self.ticket_entity_field_names(data, "ticket"),
            {
                "ticket_public_id",
                "fecha",
                "estado",
                "nombre_referencia",
                "origen_ingreso_public_id",
                "monto_total",
                "monto_material_cobrado",
                "monto_total_cobrado",
                "notas",
                "lineas",
            },
        )
        self.assertEqual(
            self.ticket_entity_field_names(data, "ticket_linea"),
            {
                "concepto_ingreso_public_id",
                "descripcion",
                "cantidad",
                "monto_unitario",
                "monto_total",
                "monto_material_cobrado",
                "orden",
                "notas",
            },
        )
        ticket_fields = {
            field["name"]: field
            for field in data["tickets"]["entities"]["ticket"]["fields"]
        }
        linea_fields = {
            field["name"]: field
            for field in data["tickets"]["entities"]["ticket_linea"]["fields"]
        }
        self.assertEqual(ticket_fields["fecha"]["type"], "datetime_utc_string")
        self.assertEqual(ticket_fields["lineas"]["type"], "array")
        self.assertEqual(
            ticket_fields["lineas"]["items_contract"],
            "chremata.ticket_line.v1",
        )
        self.assertEqual(linea_fields["cantidad"]["type"], "decimal_string")
        self.assertEqual(linea_fields["monto_unitario"]["type"], "money_string")
        self.assertEqual(linea_fields["monto_total"]["type"], "money_string")
        self.assertEqual(
            linea_fields["monto_material_cobrado"]["type"],
            "money_string",
        )

    def test_declara_campos_de_ticket_pago(self):
        data = self.get_schema().json()
        fields = {
            field["name"]: field
            for field in data["tickets"]["entities"]["ticket_pago"]["fields"]
        }

        self.assertEqual(
            set(fields),
            {
                "ticket_public_id",
                "fecha_cobro",
                "canal_cobro_public_id",
                "esquema_comision_public_id",
                "concepto_ingreso_resumen_public_id",
                "notas",
            },
        )
        self.assertEqual(fields["fecha_cobro"]["type"], "datetime_utc_string")
        self.assertEqual(fields["canal_cobro_public_id"]["type"], "uuid")
        self.assertEqual(fields["esquema_comision_public_id"]["type"], "uuid")
        self.assertFalse(fields["esquema_comision_public_id"]["required"])
        self.assertTrue(fields["esquema_comision_public_id"]["nullable"])

    def test_declara_reglas_de_tickets(self):
        rules = self.get_schema().json()["tickets"]["rules"]

        self.assertFalse(rules["ticket_pendiente_genera_ingreso"])
        self.assertFalse(rules["ticket_cancelado_genera_ingreso"])
        self.assertFalse(rules["ticket_abandonado_genera_ingreso"])
        self.assertTrue(rules["solo_cobrar_ticket_genera_ticket_pago_e_ingreso"])
        self.assertTrue(rules["material_pool_se_afecta_solo_con_ingreso_oficial"])
        self.assertTrue(rules["metricas_por_concepto_salen_de_ticket_linea"])
        self.assertTrue(rules["dinero_oficial_sale_de_ingreso"])
        self.assertTrue(rules["nombre_referencia_es_referencia_operativa"])
        self.assertEqual(
            rules["prohibe_datos_clinicos"],
            ["diagnosticos", "recetas", "tratamientos", "expedientes"],
        )

    def test_declara_operaciones_futuras_de_tickets(self):
        operations = self.get_schema().json()["operations"]

        self.assertEqual(
            operations["crear_ticket"]["contract"],
            "chremata.operation.crear_ticket.v1",
        )
        self.assertEqual(
            operations["cobrar_ticket"]["contract"],
            "chremata.operation.cobrar_ticket.v1",
        )
        self.assertEqual(
            operations["cancelar_ticket"]["contract"],
            "chremata.operation.cancelar_ticket.v1",
        )
        self.assertEqual(
            operations["abandonar_ticket"]["contract"],
            "chremata.operation.abandonar_ticket.v1",
        )
        for name in (
            "crear_ticket",
            "cobrar_ticket",
            "cancelar_ticket",
            "abandonar_ticket",
        ):
            self.assertEqual(operations[name]["method"], "POST")
            self.assertEqual(
                operations[name]["future_endpoint"],
                "/api/v1/chremata/operations/",
            )
            self.assertEqual(
                operations[name]["idempotency_key"],
                ["device_id", "device_entry_id"],
            )

    def test_crear_ticket_incluye_lineas_como_array(self):
        data = self.get_schema().json()
        crear_ticket = self.operation_payload_fields_by_name(data, "crear_ticket")
        ticket_fields = {
            field["name"]: field
            for field in data["operations"]["crear_ticket"]["ticket_fields"]
        }

        self.assertEqual(crear_ticket["ticket"]["type"], "object")
        self.assertEqual(crear_ticket["ticket"]["contract"], "chremata.ticket.v1")
        self.assertEqual(ticket_fields["lineas"]["type"], "array")
        self.assertEqual(
            ticket_fields["lineas"]["items_contract"],
            "chremata.ticket_line.v1",
        )

    def test_cobrar_ticket_declara_referencias_de_cobro(self):
        data = self.get_schema().json()
        fields = self.operation_payload_fields_by_name(data, "cobrar_ticket")

        self.assertIn("canal_cobro_public_id", fields)
        self.assertIn("esquema_comision_public_id", fields)
        self.assertIn("concepto_ingreso_resumen_public_id", fields)
        self.assertEqual(
            fields["canal_cobro_public_id"]["relation"],
            "canales_cobro.public_id",
        )
        self.assertEqual(
            fields["esquema_comision_public_id"]["relation"],
            "esquemas_comision.public_id",
        )
        self.assertFalse(fields["esquema_comision_public_id"]["required"])
        self.assertTrue(fields["esquema_comision_public_id"]["nullable"])
        self.assertEqual(
            fields["concepto_ingreso_resumen_public_id"]["relation"],
            "conceptos_ingreso.public_id",
        )
        self.assertEqual(fields["fecha_cobro"]["type"], "datetime_utc_string")
        self.assertTrue(
            data["operations"]["cobrar_ticket"]["server_authority"][
                "creates_ingreso_oficial"
            ]
        )

    def test_schema_sigue_declarando_material_pool(self):
        self.assertIn("material_pool", self.get_schema().json())

    def test_declara_los_cinco_catalogos(self):
        catalogs = self.get_schema().json()["catalogs"]

        self.assertEqual(
            set(catalogs),
            {
                "metodos_pago",
                "canales_cobro",
                "esquemas_comision",
                "conceptos_ingreso",
                "origenes_ingreso",
            },
        )
        for catalog in catalogs.values():
            self.assertEqual(catalog["identity"], "public_id")

    def test_declara_campos_de_catalogos_y_relaciones_por_public_id(self):
        data = self.get_schema().json()

        self.assertEqual(
            self.catalog_field_names(data, "metodos_pago"),
            {"public_id", "nombre"},
        )
        self.assertEqual(
            self.catalog_field_names(data, "canales_cobro"),
            {
                "public_id",
                "nombre",
                "metodo_pago_public_id",
                "metodo_pago",
                "esquema_comision_predeterminado_public_id",
            },
        )
        canales_fields = data["catalogs"]["canales_cobro"]["fields"]
        metodo_field = next(
            field
            for field in canales_fields
            if field["name"] == "metodo_pago_public_id"
        )
        esquema_field = next(
            field
            for field in canales_fields
            if field["name"] == "esquema_comision_predeterminado_public_id"
        )
        self.assertEqual(metodo_field["relation"], "metodos_pago.public_id")
        self.assertEqual(esquema_field["relation"], "esquemas_comision.public_id")
        self.assertFalse(esquema_field["required"])
        self.assertTrue(esquema_field["nullable"])

        esquema_fields = data["catalogs"]["esquemas_comision"]["fields"]
        canales_relation_field = next(
            field
            for field in esquema_fields
            if field["name"] == "canales_cobro_public_ids"
        )
        self.assertEqual(
            canales_relation_field["relation"],
            "canales_cobro.public_id",
        )

    def test_declara_decimales_como_decimal_string_o_money_string(self):
        data = self.get_schema().json()
        esquemas = {
            field["name"]: field["type"]
            for field in data["catalogs"]["esquemas_comision"]["fields"]
        }
        conceptos = {
            field["name"]: field["type"]
            for field in data["catalogs"]["conceptos_ingreso"]["fields"]
        }
        crear_ingreso = {
            field["name"]: field["type"]
            for field in data["operations"]["crear_ingreso"]["payload_fields"]
        }
        crear_gasto = {
            field["name"]: field["type"]
            for field in data["operations"]["crear_gasto_material"]["payload_fields"]
        }
        ticket_linea = {
            field["name"]: field["type"]
            for field in data["tickets"]["entities"]["ticket_linea"]["fields"]
        }

        self.assertEqual(esquemas["porcentaje_base"], "decimal_string")
        self.assertEqual(esquemas["porcentaje_iva"], "decimal_string")
        self.assertEqual(esquemas["porcentaje_total"], "decimal_string")
        self.assertEqual(conceptos["monto_material_sugerido"], "money_string")
        self.assertEqual(crear_ingreso["monto_procedimiento"], "money_string")
        self.assertEqual(crear_ingreso["monto_material_cobrado"], "money_string")
        self.assertEqual(crear_gasto["monto"], "money_string")
        self.assertEqual(ticket_linea["cantidad"], "decimal_string")
        self.assertEqual(ticket_linea["monto_unitario"], "money_string")
        self.assertEqual(ticket_linea["monto_total"], "money_string")
        self.assertEqual(ticket_linea["monto_material_cobrado"], "money_string")

    def test_declara_operaciones_futuras(self):
        operations = self.get_schema().json()["operations"]

        self.assertEqual(
            set(operations),
            {
                "crear_ingreso",
                "crear_gasto_material",
                "crear_ticket",
                "cobrar_ticket",
                "cancelar_ticket",
                "abandonar_ticket",
            },
        )
        self.assertEqual(
            operations["crear_ingreso"]["contract"],
            "chremata.operation.crear_ingreso.v1",
        )
        self.assertEqual(operations["crear_ingreso"]["method"], "POST")
        self.assertEqual(
            operations["crear_ingreso"]["future_endpoint"],
            "/api/v1/chremata/operations/",
        )
        self.assertEqual(
            operations["crear_ingreso"]["idempotency_key"],
            ["device_id", "device_entry_id"],
        )
        self.assertEqual(
            operations["crear_ingreso"]["required_top_level_fields"],
            [
                "schema_version",
                "operation_type",
                "device_entry_id",
                "device_id",
                "catalog_snapshot_id",
                "catalog_snapshot_generated_at",
                "capturado_en_device",
                "device_timezone",
                "payload",
            ],
        )
        self.assertEqual(
            self.operation_payload_field_names(
                self.get_schema().json(), "crear_ingreso"
            ),
            {
                "concepto_ingreso_public_id",
                "origen_ingreso_public_id",
                "canal_cobro_public_id",
                "metodo_pago_public_id",
                "esquema_comision_public_id",
                "monto_procedimiento",
                "monto_material_cobrado",
                "notas",
            },
        )
        self.assertEqual(
            operations["crear_gasto_material"]["contract"],
            "chremata.operation.crear_gasto_material.v1",
        )
        self.assertEqual(
            self.operation_payload_field_names(
                self.get_schema().json(), "crear_gasto_material"
            ),
            {"fecha", "monto", "descripcion", "notas"},
        )

    def test_declara_autoridad_del_servidor_para_operaciones(self):
        operations = self.get_schema().json()["operations"]

        self.assertEqual(
            operations["crear_ingreso"]["server_authority"],
            {
                "recalculates_commission": True,
                "recalculates_material_pool": True,
                "validates_catalog_public_ids": True,
                "device_calculations_are_audit_snapshot": True,
            },
        )
        self.assertEqual(
            operations["crear_gasto_material"]["server_authority"],
            {
                "updates_material_pool": True,
                "device_values_are_input_not_authority": True,
            },
        )

    def test_schema_no_declara_ids_internos_como_campos_publicos(self):
        data = self.get_schema().json()
        campos_prohibidos = {
            "id",
            "metodo_pago_id",
            "esquema_comision_predeterminado_id",
            "canales_cobro_ids",
        }

        catalog_fields = set()
        for catalog in data["catalogs"].values():
            catalog_fields.update(field["name"] for field in catalog["fields"])

        operation_fields = set()
        for operation in data["operations"].values():
            operation_fields.update(
                field["name"] for field in operation["payload_fields"]
            )

        self.assertFalse(catalog_fields & campos_prohibidos)
        self.assertFalse(operation_fields & campos_prohibidos)
