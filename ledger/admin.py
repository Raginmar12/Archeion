from django.contrib import admin

from .models import (
    CanalCobro,
    ConceptoIngreso,
    EsquemaComision,
    Ingreso,
    MetodoPago,
    OrigenIngreso,
)


@admin.register(ConceptoIngreso)
class ConceptoIngresoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo")
    search_fields = ("nombre", "descripcion")
    list_filter = ("activo",)


@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo")
    search_fields = ("nombre",)
    list_filter = ("activo",)


@admin.register(CanalCobro)
class CanalCobroAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "metodo_pago",
        "esquema_comision_predeterminado",
        "activo",
    )
    search_fields = (
        "nombre",
        "metodo_pago__nombre",
        "esquema_comision_predeterminado__nombre",
    )
    list_filter = ("metodo_pago", "esquema_comision_predeterminado", "activo")


@admin.register(EsquemaComision)
class EsquemaComisionAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "porcentaje_base",
        "cobra_iva",
        "porcentaje_iva",
        "porcentaje_total",
        "activo",
    )
    filter_horizontal = ("canales_cobro",)
    search_fields = ("nombre", "canales_cobro__nombre", "notas")
    list_filter = ("canales_cobro", "cobra_iva", "activo", "fecha_referencia")


@admin.register(OrigenIngreso)
class OrigenIngresoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo")
    search_fields = ("nombre", "descripcion")
    list_filter = ("activo",)


@admin.register(Ingreso)
class IngresoAdmin(admin.ModelAdmin):
    list_display = (
        "fecha",
        "monto_bruto",
        "comision",
        "monto_neto",
        "concepto",
        "metodo_pago_derivado",
        "canal_cobro",
        "esquema_comision",
        "origen",
    )
    search_fields = (
        "notas",
        "concepto__nombre",
        "origen__nombre",
        "canal_cobro__nombre",
        "canal_cobro__metodo_pago__nombre",
        "esquema_comision__nombre",
    )
    list_filter = (
        "concepto",
        "canal_cobro",
        "canal_cobro__metodo_pago",
        "esquema_comision",
        "origen",
        "fecha",
        "comision_manual",
    )
    date_hierarchy = "fecha"

    @admin.display(description="método de pago", ordering="canal_cobro__metodo_pago")
    def metodo_pago_derivado(self, obj):
        return obj.metodo_pago
