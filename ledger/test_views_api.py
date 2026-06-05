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
        self.origen = OrigenIngreso.objects.create(nombre="Consultorio")
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
            {self.origen.nombre},
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
            [origen_alfabetico.id, self.origen.id],
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

    def test_decimales_se_devuelven_como_strings(self):
        catalogs = self.get_catalogos().json()["catalogs"]
        esquema = catalogs["esquemas_comision"][0]
        concepto = catalogs["conceptos_ingreso"][0]

        self.assertIsInstance(esquema["porcentaje_base"], str)
        self.assertIsInstance(esquema["porcentaje_iva"], str)
        self.assertIsInstance(esquema["porcentaje_total"], str)
        self.assertIsInstance(concepto["monto_material_sugerido"], str)
