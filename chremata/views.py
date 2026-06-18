from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from .models import CajaSesion, GastoMaterial, TicketPago
from .reports import (
    calcular_reporte_chremata_periodo,
    construir_periodo_dia,
    construir_periodo_mes,
    construir_periodo_semana,
)
from .views_api import _material_pool_snapshot


@login_required
def dashboard(request):
    fecha_hoy = timezone.localdate()
    inicio_dia, fin_dia = construir_periodo_dia(fecha_hoy)
    inicio_semana, fin_semana = construir_periodo_semana(fecha_hoy)
    inicio_mes, fin_mes = construir_periodo_mes(fecha_hoy.year, fecha_hoy.month)

    reporte_hoy = calcular_reporte_chremata_periodo(
        inicio_dia,
        fin_dia,
        tipo_periodo="dia",
    )
    reporte_semana = calcular_reporte_chremata_periodo(
        inicio_semana,
        fin_semana,
        tipo_periodo="semana",
    )
    reporte_mes = calcular_reporte_chremata_periodo(
        inicio_mes,
        fin_mes,
        tipo_periodo="mes",
    )

    caja_abierta = (
        CajaSesion.objects.filter(estado=CajaSesion.ESTADO_ABIERTA)
        .select_related("caja_fisica")
        .order_by("-abierta_en")
        .first()
    )
    ultima_caja = (
        CajaSesion.objects.select_related("caja_fisica").order_by("-abierta_en").first()
    )
    caja_resumen = caja_abierta or ultima_caja

    ultimos_cobros = (
        TicketPago.objects.select_related(
            "ticket",
            "ingreso",
            "canal_cobro",
            "canal_cobro__metodo_pago",
        )
        .order_by("-fecha", "-id")[:5]
    )
    ultimos_gastos = (
        GastoMaterial.objects.select_related("caja_sesion", "caja_sesion__caja_fisica")
        .order_by("-fecha", "-id")[:5]
    )

    contexto = {
        "fecha_hoy": fecha_hoy,
        "timezone_actual": reporte_hoy["periodo"]["timezone"],
        "reporte_hoy": reporte_hoy,
        "reporte_semana": reporte_semana,
        "reporte_mes": reporte_mes,
        "caja_abierta": caja_abierta,
        "caja_resumen": caja_resumen,
        "material_pool": _material_pool_snapshot(),
        "ultimos_cobros": ultimos_cobros,
        "ultimos_gastos": ultimos_gastos,
    }
    return render(request, "chremata/dashboard.html", contexto)


@login_required
def reporte_diario(request):
    fecha_param = request.GET.get("fecha")
    advertencia = ""

    if fecha_param:
        try:
            fecha_consultada = date.fromisoformat(fecha_param)
        except ValueError:
            fecha_consultada = timezone.localdate()
            advertencia = (
                "La fecha indicada no tiene formato válido. "
                "Se muestra el reporte del día local actual."
            )
    else:
        fecha_consultada = timezone.localdate()

    inicio, fin = construir_periodo_dia(fecha_consultada)
    reporte = calcular_reporte_chremata_periodo(inicio, fin, tipo_periodo="dia")

    contexto = {
        "advertencia": advertencia,
        "fecha_consultada": fecha_consultada,
        "fecha_anterior": fecha_consultada - timedelta(days=1),
        "fecha_siguiente": fecha_consultada + timedelta(days=1),
        "fecha_hoy": timezone.localdate(),
        "reporte": reporte,
    }
    return render(request, "chremata/reportes/dia.html", contexto)
