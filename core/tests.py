from io import StringIO
from unittest.mock import patch

from django.contrib import admin
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .admin import DeviceTokenAdmin
from .models import DeviceToken


class DeviceTokenModelTests(TestCase):
    @patch("core.models.secrets.token_urlsafe", return_value="secreto-prueba-muy-largo-para-prefijo")
    def test_crear_token_guarda_hash_y_no_token_plano(self, token_urlsafe):
        device_token, token_completo = DeviceToken.crear("Cardputer principal")

        token_urlsafe.assert_called_once_with(32)
        self.assertEqual(token_completo, "archeion_secreto-prueba-muy-largo-para-prefijo")
        self.assertEqual(device_token.token_hash, DeviceToken.calcular_hash(token_completo))
        self.assertNotEqual(device_token.token_hash, token_completo)
        self.assertEqual(device_token.prefijo, token_completo[:24])
        self.assertNotIn(token_completo, str(device_token.__dict__))


class CrearDeviceTokenCommandTests(TestCase):
    @patch("core.models.secrets.token_urlsafe", return_value="secreto-comando")
    def test_comando_genera_token_y_crea_registro(self, token_urlsafe):
        salida = StringIO()

        call_command(
            "crear_device_token",
            "Cardputer principal",
            notas="Cardputer Adv",
            stdout=salida,
        )

        token_completo = "archeion_secreto-comando"
        device_token = DeviceToken.objects.get(nombre="Cardputer principal")
        self.assertEqual(device_token.notas, "Cardputer Adv")
        self.assertEqual(device_token.token_hash, DeviceToken.calcular_hash(token_completo))
        self.assertIn(token_completo, salida.getvalue())
        self.assertIn("se muestra una sola vez", salida.getvalue())
        token_urlsafe.assert_called_once_with(32)

    def test_comando_falla_si_nombre_ya_existe(self):
        DeviceToken.crear("Cardputer principal")

        with self.assertRaisesMessage(CommandError, "Ya existe un token de dispositivo"):
            call_command("crear_device_token", "Cardputer principal")


class DeviceTokenAdminTests(TestCase):
    def setUp(self):
        self.model_admin = DeviceTokenAdmin(DeviceToken, admin.site)
        self.request = RequestFactory().get("/admin/core/devicetoken/add/")

    def test_admin_no_permite_agregar_token(self):
        self.assertFalse(self.model_admin.has_add_permission(self.request))

    def test_admin_no_expone_token_completo_y_hash_es_solo_lectura(self):
        device_token, token_completo = DeviceToken.crear("Script local")

        self.assertNotIn(token_completo, self.model_admin.get_readonly_fields(self.request))
        self.assertIn("token_hash", self.model_admin.get_readonly_fields(self.request))
        self.assertIn("prefijo", self.model_admin.get_readonly_fields(self.request))
        self.assertNotIn(token_completo, str(device_token.__dict__))


class DeviceTokenMiddlewareTests(TestCase):
    @override_settings(DEBUG=False, ARCHEION_DEVICE_TOKEN="fallback-no-debe-usarse")
    def test_token_valido_de_base_de_datos_permite_api_y_actualiza_ultimo_uso(self):
        device_token, token_completo = DeviceToken.crear("Cardputer principal")

        response = self.client.get(
            reverse("device-ping"),
            headers={"X-Archeion-Device-Token": token_completo},
        )

        self.assertEqual(response.status_code, 200)
        device_token.refresh_from_db()
        self.assertIsNotNone(device_token.ultimo_uso_en)

    @override_settings(DEBUG=False, ARCHEION_DEVICE_TOKEN="fallback-no-debe-usarse")
    def test_token_valido_de_base_de_datos_permite_post_sin_csrf(self):
        _, token_completo = DeviceToken.crear("Módulo de avisos")

        response = self.client.post(
            reverse("device-ping"),
            headers={"X-Archeion-Device-Token": token_completo},
        )

        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=False, ARCHEION_DEVICE_TOKEN="fallback-no-debe-usarse")
    def test_fallback_no_se_acepta_si_hay_tokens_activos(self):
        DeviceToken.crear("Cardputer principal")

        response = self.client.get(
            reverse("device-ping"),
            headers={"X-Archeion-Device-Token": "fallback-no-debe-usarse"},
        )

        self.assertEqual(response.status_code, 401)

    @override_settings(DEBUG=True, ARCHEION_DEVICE_TOKEN="")
    def test_token_invalido_responde_401_si_hay_tokens_activos(self):
        DeviceToken.crear("Cardputer principal")

        response = self.client.get(
            reverse("device-ping"),
            headers={"X-Archeion-Device-Token": "incorrecto"},
        )

        self.assertEqual(response.status_code, 401)

    @override_settings(DEBUG=True, ARCHEION_DEVICE_TOKEN="")
    def test_token_ausente_responde_401_si_hay_tokens_activos(self):
        DeviceToken.crear("Cardputer principal")

        response = self.client.get(reverse("device-ping"))

        self.assertEqual(response.status_code, 401)

    @override_settings(DEBUG=False, ARCHEION_DEVICE_TOKEN="")
    def test_token_inactivo_responde_401_si_hay_otro_token_activo(self):
        token_inactivo, token_completo_inactivo = DeviceToken.crear("Cardputer respaldo")
        token_inactivo.activo = False
        token_inactivo.save()
        DeviceToken.crear("Cardputer principal")

        response = self.client.get(
            reverse("device-ping"),
            headers={"X-Archeion-Device-Token": token_completo_inactivo},
        )

        self.assertEqual(response.status_code, 401)

    @override_settings(DEBUG=False, ARCHEION_DEVICE_TOKEN="token-fallback")
    def test_sin_tokens_activos_fallback_global_sigue_funcionando(self):
        token_inactivo, _ = DeviceToken.crear("Cardputer respaldo")
        token_inactivo.activo = False
        token_inactivo.save()

        response = self.client.get(
            reverse("device-ping"),
            headers={"X-Archeion-Device-Token": "token-fallback"},
        )

        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=True, ARCHEION_DEVICE_TOKEN="")
    def test_sin_tokens_activos_ni_fallback_debug_permite_api(self):
        response = self.client.get(reverse("device-ping"))

        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=False, ARCHEION_DEVICE_TOKEN="")
    def test_sin_tokens_activos_ni_fallback_produccion_responde_503(self):
        response = self.client.get(reverse("device-ping"))

        self.assertEqual(response.status_code, 503)
