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
    list_display = ("nombre", "metodo_pago", "activo")
    search_fields = ("nombre", "metodo_pago__nombre")
    list_filter = ("metodo_pago", "activo")


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
        "metodo_pago",
        "canal_cobro",
        "esquema_comision",
        "origen",
    )
    search_fields = (
        "notas",
        "concepto__nombre",
        "origen__nombre",
        "canal_cobro__nombre",
    )
    list_filter = (
        "concepto",
        "metodo_pago",
        "canal_cobro",
        "esquema_comision",
        "origen",
        "fecha",
        "comision_manual",
    )
    date_hierarchy = "fecha"
