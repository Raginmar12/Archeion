from django.contrib import admin

from .models import (
    CajaFisica,
    CajaSesion,
    CanalCobro,
    ConceptoIngreso,
    EsquemaComision,
    GastoMaterial,
    OperacionDispositivoChremata,
    Ingreso,
    MetodoPago,
    OrigenIngreso,
    Ticket,
    TicketLinea,
    TicketPago,
)


@admin.register(CajaFisica)
class CajaFisicaAdmin(admin.ModelAdmin):
    readonly_fields = ("public_id",)
    list_display = ("nombre", "activa", "actualizado_en")
    search_fields = ("nombre", "descripcion", "notas")
    list_filter = ("activa",)


@admin.register(CajaSesion)
class CajaSesionAdmin(admin.ModelAdmin):
    readonly_fields = ("public_id",)
    list_display = (
        "public_id",
        "device_id",
        "caja_fisica",
        "estado",
        "abierta_en",
        "cerrada_en",
        "total_bruto",
        "diferencia_efectivo",
    )
    search_fields = (
        "public_id",
        "device_id",
        "caja_fisica__nombre",
        "notas_apertura",
        "notas_cierre",
    )
    list_filter = ("estado", "caja_fisica", "abierta_en", "cerrada_en")
    date_hierarchy = "abierta_en"


@admin.register(ConceptoIngreso)
class ConceptoIngresoAdmin(admin.ModelAdmin):
    readonly_fields = ("public_id",)
    list_display = (
        "nombre",
        "permite_material_adicional",
        "monto_material_sugerido",
        "activo",
    )
    search_fields = ("nombre", "descripcion")
    list_filter = ("permite_material_adicional", "activo")


@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    readonly_fields = ("public_id",)
    list_display = ("nombre", "activo")
    search_fields = ("nombre",)
    list_filter = ("activo",)


@admin.register(CanalCobro)
class CanalCobroAdmin(admin.ModelAdmin):
    readonly_fields = ("public_id",)
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
    readonly_fields = ("public_id",)
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
    readonly_fields = ("public_id",)
    list_display = ("nombre", "activo")
    search_fields = ("nombre", "descripcion")
    list_filter = ("activo",)


@admin.register(GastoMaterial)
class GastoMaterialAdmin(admin.ModelAdmin):
    list_display = ("fecha", "monto", "descripcion", "caja_sesion")
    search_fields = ("descripcion", "notas")
    list_filter = ("fecha", "caja_sesion")
    date_hierarchy = "fecha"


@admin.register(Ingreso)
class IngresoAdmin(admin.ModelAdmin):
    list_display = (
        "fecha",
        "monto_procedimiento",
        "monto_material_cobrado",
        "monto_total",
        "comision",
        "monto_neto",
        "material_recuperado",
        "material_excedente",
        "concepto",
        "metodo_pago_derivado",
        "canal_cobro",
        "esquema_comision",
        "origen",
        "caja_sesion",
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
        "concepto__permite_material_adicional",
        "canal_cobro",
        "canal_cobro__metodo_pago",
        "esquema_comision",
        "origen",
        "caja_sesion",
        "fecha",
        "comision_manual",
    )
    date_hierarchy = "fecha"

    @admin.display(description="método de pago", ordering="canal_cobro__metodo_pago")
    def metodo_pago_derivado(self, obj):
        return obj.metodo_pago


class TicketLineaInline(admin.TabularInline):
    model = TicketLinea
    extra = 1
    readonly_fields = ("monto_total",)
    fields = (
        "orden",
        "concepto",
        "descripcion",
        "cantidad",
        "monto_unitario",
        "monto_total",
        "monto_material_cobrado",
        "notas",
    )


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    readonly_fields = ("public_id", "monto_total", "monto_material_cobrado")
    inlines = (TicketLineaInline,)
    list_display = (
        "fecha",
        "estado",
        "nombre_referencia",
        "origen",
        "monto_total",
        "monto_material_cobrado",
        "creado_en",
    )
    search_fields = ("nombre_referencia", "notas", "origen__nombre")
    list_filter = ("estado", "origen", "fecha")
    date_hierarchy = "fecha"


@admin.register(TicketLinea)
class TicketLineaAdmin(admin.ModelAdmin):
    readonly_fields = ("monto_total",)
    list_display = (
        "ticket",
        "orden",
        "concepto",
        "cantidad",
        "monto_unitario",
        "monto_total",
        "monto_material_cobrado",
    )
    search_fields = (
        "ticket__nombre_referencia",
        "concepto__nombre",
        "descripcion",
        "notas",
    )
    list_filter = ("concepto", "ticket__estado")


@admin.register(TicketPago)
class TicketPagoAdmin(admin.ModelAdmin):
    readonly_fields = ("ingreso",)
    list_display = (
        "ticket",
        "ingreso",
        "fecha",
        "canal_cobro",
        "esquema_comision",
        "concepto_ingreso",
        "caja_sesion",
        "creado_en",
    )
    search_fields = (
        "ticket__id",
        "ticket__public_id",
        "ticket__nombre_referencia",
        "ingreso__id",
    )
    list_filter = (
        "canal_cobro",
        "esquema_comision",
        "concepto_ingreso",
        "caja_sesion",
        "fecha",
    )
    date_hierarchy = "fecha"


@admin.register(OperacionDispositivoChremata)
class OperacionDispositivoChremataAdmin(admin.ModelAdmin):
    readonly_fields = ("recibido_en", "procesado_en", "actualizado_en")
    list_display = (
        "device_id",
        "device_entry_id",
        "operation",
        "status",
        "caja_sesion",
        "ticket",
        "ingreso",
        "ticket_pago",
        "gasto_material",
        "recibido_en",
    )
    search_fields = ("device_id", "device_entry_id", "operation")
    list_filter = ("operation", "status", "caja_sesion", "recibido_en")
    date_hierarchy = "recibido_en"
