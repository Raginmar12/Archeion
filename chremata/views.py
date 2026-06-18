from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from .reports import calcular_reporte_chremata_periodo, construir_periodo_dia


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
