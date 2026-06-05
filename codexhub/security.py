from hmac import compare_digest

from django.conf import settings
from django.http import JsonResponse


DEVICE_TOKEN_HEADER = "HTTP_X_CODEX_DEVICE_TOKEN"
API_PATH_PREFIX = "/api/"


class DeviceTokenMiddleware:
    """Protege endpoints locales bajo /api/ con el token de dispositivos."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith(API_PATH_PREFIX):
            respuesta_denegada = self._validar_token(request)
            if respuesta_denegada:
                return respuesta_denegada

            # El token de dispositivo sustituye CSRF únicamente dentro de /api/.
            request._dont_enforce_csrf_checks = True

        return self.get_response(request)

    @staticmethod
    def _validar_token(request):
        token_configurado = settings.CODEX_DEVICE_TOKEN

        if not token_configurado:
            if settings.DEBUG:
                return None
            return JsonResponse(
                {"detail": "Acceso API deshabilitado: token de dispositivo no configurado."},
                status=503,
            )

        token_recibido = request.META.get(DEVICE_TOKEN_HEADER, "")
        if not token_recibido or not compare_digest(token_recibido, token_configurado):
            return JsonResponse(
                {"detail": "Token de dispositivo inválido o ausente."},
                status=401,
            )

        return None
