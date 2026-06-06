from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import DeviceToken

from .models import (
    CanalCobro,
    ConceptoIngreso,
    EsquemaComision,
    MetodoPago,
    OrigenIngreso,
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

        self.assertEqual(esquemas["porcentaje_base"], "decimal_string")
        self.assertEqual(esquemas["porcentaje_iva"], "decimal_string")
        self.assertEqual(esquemas["porcentaje_total"], "decimal_string")
        self.assertEqual(conceptos["monto_material_sugerido"], "money_string")
        self.assertEqual(crear_ingreso["monto_procedimiento"], "money_string")
        self.assertEqual(crear_ingreso["monto_material_cobrado"], "money_string")
        self.assertEqual(crear_gasto["monto"], "money_string")

    def test_declara_operaciones_futuras(self):
        operations = self.get_schema().json()["operations"]

        self.assertEqual(set(operations), {"crear_ingreso", "crear_gasto_material"})
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
