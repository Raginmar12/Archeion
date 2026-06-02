from django.contrib import admin

from .models import ConceptoIngreso, Ingreso, MetodoPago, OrigenIngreso


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


@admin.register(OrigenIngreso)
class OrigenIngresoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo")
    search_fields = ("nombre", "descripcion")
    list_filter = ("activo",)


@admin.register(Ingreso)
class IngresoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "monto", "concepto", "metodo_pago", "origen")
    search_fields = ("notas", "concepto__nombre", "origen__nombre")
    list_filter = ("concepto", "metodo_pago", "origen", "fecha")
    date_hierarchy = "fecha"