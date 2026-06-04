from django.test import TestCase, override_settings
from django.urls import reverse


class DeviceTokenSecurityTests(TestCase):
    @override_settings(DEBUG=True, CODEX_DEVICE_TOKEN="")
    def test_debug_sin_token_configurado_permite_api(self):
        response = self.client.get(reverse("device-ping"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    @override_settings(DEBUG=False, CODEX_DEVICE_TOKEN="")
    def test_produccion_sin_token_configurado_deniega_api(self):
        response = self.client.get(reverse("device-ping"))

        self.assertEqual(response.status_code, 503)

    @override_settings(DEBUG=True, CODEX_DEVICE_TOKEN="token-secreto")
    def test_token_configurado_se_exige_incluso_en_debug(self):
        response = self.client.get(reverse("device-ping"))

        self.assertEqual(response.status_code, 401)

    @override_settings(DEBUG=False, CODEX_DEVICE_TOKEN="token-secreto")
    def test_token_invalido_deniega_api(self):
        response = self.client.get(
            reverse("device-ping"),
            headers={"X-Codex-Device-Token": "incorrecto"},
        )

        self.assertEqual(response.status_code, 401)

    @override_settings(DEBUG=False, CODEX_DEVICE_TOKEN="token-secreto")
    def test_token_valido_permite_api(self):
        response = self.client.get(
            reverse("device-ping"),
            headers={"X-Codex-Device-Token": "token-secreto"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    @override_settings(DEBUG=False, CODEX_DEVICE_TOKEN="token-secreto")
    def test_token_valido_permite_post_api_sin_csrf(self):
        response = self.client.post(
            reverse("device-ping"),
            headers={"X-Codex-Device-Token": "token-secreto"},
        )

        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=False, CODEX_DEVICE_TOKEN="token-secreto")
    def test_admin_no_usa_proteccion_de_token_de_dispositivo(self):
        response = self.client.get("/admin/login/")

        self.assertEqual(response.status_code, 200)
