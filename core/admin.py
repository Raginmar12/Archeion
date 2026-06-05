from django.contrib import admin

from .models import DeviceToken


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "prefijo",
        "activo",
        "ultimo_uso_en",
        "creado_en",
        "actualizado_en",
    )
    search_fields = ("nombre", "prefijo", "notas")
    list_filter = ("activo", "creado_en", "ultimo_uso_en")
    readonly_fields = (
        "token_hash",
        "prefijo",
        "ultimo_uso_en",
        "creado_en",
        "actualizado_en",
    )
    fields = (
        "nombre",
        "prefijo",
        "token_hash",
        "activo",
        "notas",
        "ultimo_uso_en",
        "creado_en",
        "actualizado_en",
    )

    def has_add_permission(self, request):
        return False
