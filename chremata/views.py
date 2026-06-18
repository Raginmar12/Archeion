from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import CajaSesion, GastoMaterial, TicketPago
from .reports import (
    calcular_reporte_chremata_periodo,
    construir_periodo_anio,
    construir_periodo_dia,
    construir_periodo_mes,
    construir_periodo_semana,
)
from .services import calcular_corte_caja
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


def _periodo_contexto(titulo, tipo_periodo, inicio, fin, advertencia="", **extra):
    reporte = calcular_reporte_chremata_periodo(inicio, fin, tipo_periodo=tipo_periodo)
    contexto = {
        "titulo": titulo,
        "tipo_periodo": tipo_periodo,
        "advertencia": advertencia,
        "reporte": reporte,
    }
    contexto.update(extra)
    return contexto


@login_required
def reporte_semana(request):
    fecha_param = request.GET.get("fecha")
    advertencia = ""
    if fecha_param:
        try:
            fecha_consultada = date.fromisoformat(fecha_param)
        except ValueError:
            fecha_consultada = timezone.localdate()
            advertencia = (
                "La fecha indicada no tiene formato válido. "
                "Se muestra la semana local actual."
            )
    else:
        fecha_consultada = timezone.localdate()

    inicio, fin = construir_periodo_semana(fecha_consultada)
    contexto = _periodo_contexto(
        "Reporte semanal Chremata",
        "semana",
        inicio,
        fin,
        advertencia,
        fecha_consultada=fecha_consultada,
        fecha_anterior=fecha_consultada - timedelta(days=7),
        fecha_siguiente=fecha_consultada + timedelta(days=7),
        fecha_hoy=timezone.localdate(),
    )
    return render(request, "chremata/reportes/periodo.html", contexto)


@login_required
def reporte_mes(request):
    hoy = timezone.localdate()
    advertencia = ""
    try:
        anio = int(request.GET.get("anio", hoy.year))
        mes = int(request.GET.get("mes", hoy.month))
        inicio, fin = construir_periodo_mes(anio, mes)
    except (TypeError, ValueError):
        anio = hoy.year
        mes = hoy.month
        inicio, fin = construir_periodo_mes(anio, mes)
        advertencia = (
            "El mes o año indicado no tiene formato válido. "
            "Se muestra el mes local actual."
        )

    mes_anterior = inicio.date() - timedelta(days=1)
    mes_siguiente = fin.date()
    contexto = _periodo_contexto(
        "Reporte mensual Chremata",
        "mes",
        inicio,
        fin,
        advertencia,
        anio=anio,
        mes=mes,
        mes_anterior_anio=mes_anterior.year,
        mes_anterior_mes=mes_anterior.month,
        mes_siguiente_anio=mes_siguiente.year,
        mes_siguiente_mes=mes_siguiente.month,
        hoy_anio=hoy.year,
        hoy_mes=hoy.month,
    )
    return render(request, "chremata/reportes/periodo.html", contexto)


@login_required
def reporte_anio(request):
    hoy = timezone.localdate()
    advertencia = ""
    try:
        anio = int(request.GET.get("anio", hoy.year))
        inicio, fin = construir_periodo_anio(anio)
    except (TypeError, ValueError):
        anio = hoy.year
        inicio, fin = construir_periodo_anio(anio)
        advertencia = (
            "El año indicado no tiene formato válido. "
            "Se muestra el año local actual."
        )

    contexto = _periodo_contexto(
        "Reporte anual Chremata",
        "anio",
        inicio,
        fin,
        advertencia,
        anio=anio,
        anio_anterior=anio - 1,
        anio_siguiente=anio + 1,
        hoy_anio=hoy.year,
    )
    return render(request, "chremata/reportes/periodo.html", contexto)



@login_required
def caja_detalle(request, public_id):
    caja = get_object_or_404(
        CajaSesion.objects.select_related("caja_fisica"),
        public_id=public_id,
    )
    corte = calcular_corte_caja(caja)
    contexto = {
        "titulo": "Corte de caja",
        "caja": caja,
        "corte": corte,
    }
    return render(request, "chremata/cajas/detalle.html", contexto)
