from hmac import compare_digest

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

from core.models import DeviceToken


DEVICE_TOKEN_HEADER = "HTTP_X_CODEX_DEVICE_TOKEN"
API_PATH_PREFIX = "/api/"


class DeviceTokenMiddleware:
    """Protege endpoints locales bajo /api/ con tokens de dispositivos."""

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
        tokens_activos = DeviceToken.objects.filter(activo=True)
        token_recibido = request.META.get(DEVICE_TOKEN_HEADER, "")

        if tokens_activos.exists():
            if not token_recibido:
                return DeviceTokenMiddleware._respuesta_token_invalido()

            token = tokens_activos.filter(
                token_hash=DeviceToken.calcular_hash(token_recibido),
            ).first()
            if not token:
                return DeviceTokenMiddleware._respuesta_token_invalido()

            DeviceToken.objects.filter(pk=token.pk).update(ultimo_uso_en=timezone.now())
            return None

        token_configurado = settings.CODEX_DEVICE_TOKEN
        if token_configurado:
            if token_recibido and compare_digest(token_recibido, token_configurado):
                return None
            return DeviceTokenMiddleware._respuesta_token_invalido()

        if settings.DEBUG:
            return None
        return JsonResponse(
            {"detail": "Acceso API deshabilitado: token de dispositivo no configurado."},
            status=503,
        )

    @staticmethod
    def _respuesta_token_invalido():
        return JsonResponse(
            {"detail": "Token de dispositivo inválido o ausente."},
            status=401,
        )
