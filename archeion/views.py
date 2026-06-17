from django.http import JsonResponse


def device_ping(request):
    """Endpoint mínimo para comprobar conectividad autenticada de dispositivos."""
    return JsonResponse({"status": "ok"})
