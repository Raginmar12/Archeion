from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import (
    CajaSesion,
    GastoMaterial,
    Ingreso,
    OperacionDispositivoChremata,
    PESOS_DECIMALES,
    Ticket,
    TicketLinea,
    TicketPago,
)

REPORTE_PERIODO_CONTRACT = "chremata.reporte_periodo.v1"


def _money(valor):
    return str((valor or Decimal("0.00")).quantize(PESOS_DECIMALES))


def _decimal_string(valor):
    return str((valor or Decimal("0.00")).quantize(PESOS_DECIMALES))


def _datetime_local(valor):
    if valor is None:
        return None
    return timezone.localtime(valor).replace(microsecond=0).isoformat()


def _timezone_name():
    tz = timezone.get_current_timezone()
    return getattr(tz, "key", str(tz))


def _local_midnight(valor):
    tz = timezone.get_current_timezone()
    if isinstance(valor, datetime):
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor, tz).date()
        else:
            valor = valor.date()
    return datetime.combine(valor, time.min, tzinfo=tz)


def construir_periodo_dia(fecha):
    inicio = _local_midnight(fecha)
    return inicio, inicio + timedelta(days=1)


def construir_periodo_semana(fecha):
    dia = _local_midnight(fecha).date()
    inicio = _local_midnight(dia - timedelta(days=dia.weekday()))
    return inicio, inicio + timedelta(days=7)


def construir_periodo_mes(anio, mes):
    inicio = _local_midnight(date(anio, mes, 1))
    if mes == 12:
        fin = _local_midnight(date(anio + 1, 1, 1))
    else:
        fin = _local_midnight(date(anio, mes + 1, 1))
    return inicio, fin


def construir_periodo_anio(anio):
    inicio = _local_midnight(date(anio, 1, 1))
    fin = _local_midnight(date(anio + 1, 1, 1))
    return inicio, fin


def _sumar(queryset, campo):
    return (queryset.aggregate(total=Sum(campo))["total"] or Decimal("0.00")).quantize(
        PESOS_DECIMALES
    )


def _serializar_totales_ingreso(items, *, id_key, name_key, extra_keys=()):
    serializados = []
    for item in items:
        serializado = {
            id_key: str(item[id_key]),
            name_key: item[name_key],
            "cantidad": item["cantidad"],
            "total_bruto": _money(item["total_bruto"]),
            "total_comisiones": _money(item.get("total_comisiones")),
            "total_neto_estimado": _money(item["total_neto_estimado"]),
        }
        for key in extra_keys:
            serializado[key] = item[key]
        serializados.append(serializado)
    return serializados


def _agrupar_ingresos_por_metodo(ingresos):
    items = (
        ingresos.values(
            "canal_cobro__metodo_pago__public_id",
            "canal_cobro__metodo_pago__nombre",
        )
        .annotate(
            cantidad=Count("id"),
            total_bruto=Sum("monto_total"),
            total_comisiones=Sum("comision"),
            total_neto_estimado=Sum("monto_neto"),
        )
        .order_by("canal_cobro__metodo_pago__nombre")
    )
    return _serializar_totales_ingreso(
        (
            {
                "metodo_pago_public_id": item["canal_cobro__metodo_pago__public_id"],
                "metodo_pago": item["canal_cobro__metodo_pago__nombre"],
                **item,
            }
            for item in items
        ),
        id_key="metodo_pago_public_id",
        name_key="metodo_pago",
    )


def _agrupar_ingresos_por_canal(ingresos):
    items = (
        ingresos.values(
            "canal_cobro__public_id",
            "canal_cobro__nombre",
            "canal_cobro__metodo_pago__nombre",
        )
        .annotate(
            cantidad=Count("id"),
            total_bruto=Sum("monto_total"),
            total_comisiones=Sum("comision"),
            total_neto_estimado=Sum("monto_neto"),
        )
        .order_by("canal_cobro__nombre")
    )
    return _serializar_totales_ingreso(
        (
            {
                "canal_cobro_public_id": item["canal_cobro__public_id"],
                "canal_cobro": item["canal_cobro__nombre"],
                "metodo_pago": item["canal_cobro__metodo_pago__nombre"],
                **item,
            }
            for item in items
        ),
        id_key="canal_cobro_public_id",
        name_key="canal_cobro",
        extra_keys=("metodo_pago",),
    )


def _agrupar_ingresos_por_origen(ingresos):
    items = (
        ingresos.values("origen__public_id", "origen__nombre")
        .annotate(
            cantidad=Count("id"),
            total_bruto=Sum("monto_total"),
            total_neto_estimado=Sum("monto_neto"),
        )
        .order_by("origen__nombre")
    )
    return [
        {
            "origen_public_id": str(item["origen__public_id"]),
            "origen": item["origen__nombre"],
            "cantidad": item["cantidad"],
            "total_bruto": _money(item["total_bruto"]),
            "total_neto_estimado": _money(item["total_neto_estimado"]),
        }
        for item in items
    ]


def _agrupar_ticket_lineas_por_concepto(inicio, fin):
    conceptos = (
        TicketLinea.objects.filter(
            ticket__pago__fecha__gte=inicio,
            ticket__pago__fecha__lt=fin,
        )
        .values("concepto__public_id", "concepto__nombre")
        .annotate(
            cantidad_total=Sum("cantidad"),
            lineas=Count("id"),
            total=Sum("monto_total"),
            material_cobrado=Sum("monto_material_cobrado"),
        )
        .order_by("concepto__nombre")
    )
    return [
        {
            "concepto_public_id": str(item["concepto__public_id"]),
            "concepto": item["concepto__nombre"],
            "cantidad_total": _decimal_string(item["cantidad_total"]),
            "lineas": item["lineas"],
            "total": _money(item["total"]),
            "material_cobrado": _money(item["material_cobrado"]),
        }
        for item in conceptos
    ]


def _agrupar_ingresos_directos_por_concepto(ingresos):
    conceptos = (
        ingresos.filter(ticket_pago__isnull=True)
        .values("concepto__public_id", "concepto__nombre")
        .annotate(
            cantidad=Count("id"),
            total_bruto=Sum("monto_total"),
            total_neto_estimado=Sum("monto_neto"),
            material_cobrado=Sum("monto_material_cobrado"),
        )
        .order_by("concepto__nombre")
    )
    return [
        {
            "concepto_public_id": str(item["concepto__public_id"]),
            "concepto": item["concepto__nombre"],
            "cantidad": item["cantidad"],
            "total_bruto": _money(item["total_bruto"]),
            "total_neto_estimado": _money(item["total_neto_estimado"]),
            "material_cobrado": _money(item["material_cobrado"]),
        }
        for item in conceptos
    ]


def _serializar_gastos_material(gastos):
    total = _sumar(gastos, "monto")
    con_caja = gastos.filter(caja_sesion__isnull=False)
    sin_caja = gastos.filter(caja_sesion__isnull=True)
    por_caja_items = (
        con_caja.values(
            "caja_sesion__public_id",
            "caja_sesion__estado",
        )
        .annotate(cantidad=Count("id"), total=Sum("monto"))
        .order_by("caja_sesion__public_id")
    )
    detalle = (
        gastos.select_related("caja_sesion")
        .order_by("fecha", "id")
        .values("fecha", "monto", "descripcion", "caja_sesion__public_id")
    )
    return {
        "cantidad": gastos.count(),
        "total": _money(total),
        "con_caja": {
            "cantidad": con_caja.count(),
            "total": _money(_sumar(con_caja, "monto")),
        },
        "sin_caja": {
            "cantidad": sin_caja.count(),
            "total": _money(_sumar(sin_caja, "monto")),
        },
        "por_caja": [
            {
                "caja_public_id": str(item["caja_sesion__public_id"]),
                "estado": item["caja_sesion__estado"],
                "cantidad": item["cantidad"],
                "total": _money(item["total"]),
            }
            for item in por_caja_items
        ],
        "detalle": [
            {
                "fecha": _datetime_local(item["fecha"]),
                "monto": _money(item["monto"]),
                "descripcion": item["descripcion"],
                "caja_public_id": str(item["caja_sesion__public_id"])
                if item["caja_sesion__public_id"]
                else None,
            }
            for item in detalle
        ],
    }


def _serializar_cajas(inicio, fin):
    cajas = (
        CajaSesion.objects.filter(abierta_en__lt=fin)
        .filter(Q(cerrada_en__isnull=True) | Q(cerrada_en__gt=inicio))
        .select_related("caja_fisica", "origen_ingreso")
        .order_by("abierta_en", "id")
    )
    cajas_lista = []
    for caja in cajas:
        caja_fisica = None
        if caja.caja_fisica_id:
            caja_fisica = {
                "public_id": str(caja.caja_fisica.public_id),
                "nombre": caja.caja_fisica.nombre,
            }
        origen_ingreso = None
        if caja.origen_ingreso_id:
            origen_ingreso = {
                "public_id": str(caja.origen_ingreso.public_id),
                "nombre": caja.origen_ingreso.nombre,
            }
        total_gastos_material_caja = (
            GastoMaterial.objects.filter(caja_sesion=caja).aggregate(total=Sum("monto"))[
                "total"
            ]
            or Decimal("0.00")
        )
        cajas_lista.append(
            {
                "caja_public_id": str(caja.public_id),
                "caja_fisica": caja_fisica,
                "origen_ingreso": origen_ingreso,
                "estado": caja.estado,
                "abierta_en": _datetime_local(caja.abierta_en),
                "cerrada_en": _datetime_local(caja.cerrada_en),
                "saldo_inicial_efectivo": _money(caja.saldo_inicial_efectivo),
                "efectivo_esperado": _money(caja.efectivo_esperado),
                "efectivo_contado_cierre": _money(caja.efectivo_contado_cierre)
                if caja.efectivo_contado_cierre is not None
                else None,
                "diferencia_efectivo": _money(caja.diferencia_efectivo),
                "total_gastos_material_caja": _money(total_gastos_material_caja),
                # Vista HTML de corte pendiente para R5.
                "corte_url": None,
            }
        )
    return {
        "cantidad": cajas.count(),
        "abiertas": cajas.filter(estado=CajaSesion.ESTADO_ABIERTA).count(),
        "cerradas": cajas.filter(estado=CajaSesion.ESTADO_CERRADA).count(),
        "intersectan_periodo": cajas_lista,
    }


def _serializar_operaciones_dispositivo(inicio, fin):
    operaciones = OperacionDispositivoChremata.objects.filter(
        recibido_en__gte=inicio,
        recibido_en__lt=fin,
    )
    por_estado = {
        item["status"]: item["cantidad"]
        for item in operaciones.values("status").annotate(cantidad=Count("id"))
    }
    return {
        "recibidas": operaciones.count(),
        "procesadas": por_estado.get(OperacionDispositivoChremata.STATUS_PROCESSED, 0),
        "fallidas": por_estado.get(OperacionDispositivoChremata.STATUS_FAILED, 0),
        "conflicto": por_estado.get(OperacionDispositivoChremata.STATUS_CONFLICT, 0),
        "pendientes": por_estado.get(OperacionDispositivoChremata.STATUS_RECEIVED, 0),
    }


def calcular_reporte_chremata_periodo(inicio, fin, *, tipo_periodo=None):
    if timezone.is_naive(inicio) or timezone.is_naive(fin):
        raise ValueError("inicio y fin deben ser datetimes timezone-aware")
    if fin <= inicio:
        raise ValueError("fin debe ser posterior a inicio")

    ingresos = Ingreso.objects.filter(fecha__gte=inicio, fecha__lt=fin).select_related(
        "canal_cobro",
        "canal_cobro__metodo_pago",
        "concepto",
        "origen",
    )
    pagos = TicketPago.objects.filter(fecha__gte=inicio, fecha__lt=fin).select_related(
        "ticket",
        "ingreso",
        "canal_cobro",
        "canal_cobro__metodo_pago",
    )
    tickets_creados = Ticket.objects.filter(fecha__gte=inicio, fecha__lt=fin)
    gastos = GastoMaterial.objects.filter(fecha__gte=inicio, fecha__lt=fin)

    total_bruto = _sumar(ingresos, "monto_total")
    total_procedimiento = _sumar(ingresos, "monto_procedimiento")
    total_material_cobrado = _sumar(ingresos, "monto_material_cobrado")
    total_material_recuperado = _sumar(ingresos, "material_recuperado")
    total_material_excedente = _sumar(ingresos, "material_excedente")
    total_comisiones = _sumar(ingresos, "comision")
    total_gastos_material = _sumar(gastos, "monto")
    total_neto_despues_comisiones = (total_bruto - total_comisiones).quantize(
        PESOS_DECIMALES
    )
    total_neto_estimado = total_neto_despues_comisiones
    utilidad_bruta_estimada = (total_bruto - total_gastos_material).quantize(
        PESOS_DECIMALES
    )
    neto_operativo_basico = (
        total_bruto - total_gastos_material - total_comisiones
    ).quantize(PESOS_DECIMALES)
    total_neto_ganado = neto_operativo_basico
    balance_material_periodo = (total_material_cobrado - total_gastos_material).quantize(
        PESOS_DECIMALES
    )

    tickets_cobrados = pagos.count()
    promedio_por_ticket = Decimal("0.00")
    if tickets_cobrados:
        total_tickets_cobrados = (
            pagos.aggregate(total=Sum("ingreso__monto_total"))["total"]
            or Decimal("0.00")
        )
        promedio_por_ticket = (total_tickets_cobrados / Decimal(tickets_cobrados)).quantize(
            PESOS_DECIMALES,
            rounding=ROUND_HALF_UP,
        )

    return {
        "contract": REPORTE_PERIODO_CONTRACT,
        "generated_at": _datetime_local(timezone.now()),
        "periodo": {
            "tipo": tipo_periodo or "personalizado",
            "inicio": _datetime_local(inicio),
            "fin": _datetime_local(fin),
            "timezone": _timezone_name(),
        },
        "totales": {
            "total_bruto": _money(total_bruto),
            "total_ingresos_cobrados": _money(total_bruto),
            "total_procedimiento": _money(total_procedimiento),
            "total_material_cobrado": _money(total_material_cobrado),
            "total_material_recuperado": _money(total_material_recuperado),
            "total_material_excedente": _money(total_material_excedente),
            "total_comisiones": _money(total_comisiones),
            "total_comisiones_cobro": _money(total_comisiones),
            "total_neto_despues_comisiones": _money(
                total_neto_despues_comisiones
            ),
            "total_neto_estimado": _money(total_neto_estimado),
            "total_neto_ganado": _money(total_neto_ganado),
            "total_gastos_material": _money(total_gastos_material),
            "total_costo_material": _money(total_gastos_material),
            "utilidad_bruta_estimada": _money(utilidad_bruta_estimada),
            "neto_operativo_basico": _money(neto_operativo_basico),
            "balance_material_periodo": _money(balance_material_periodo),
        },
        "actividad": {
            "tickets_cobrados": tickets_cobrados,
            "ingresos": ingresos.count(),
            "tickets_creados": tickets_creados.count(),
            "tickets_pendientes_creados": tickets_creados.filter(
                estado=Ticket.ESTADO_PENDIENTE
            ).count(),
            "tickets_cancelados_creados": tickets_creados.filter(
                estado=Ticket.ESTADO_CANCELADO
            ).count(),
            "tickets_abandonados_creados": tickets_creados.filter(
                estado=Ticket.ESTADO_ABANDONADO
            ).count(),
            "promedio_por_ticket": _money(promedio_por_ticket),
        },
        "por_metodo": _agrupar_ingresos_por_metodo(ingresos),
        "por_canal": _agrupar_ingresos_por_canal(ingresos),
        "por_concepto": _agrupar_ticket_lineas_por_concepto(inicio, fin),
        "por_origen": _agrupar_ingresos_por_origen(ingresos),
        "ingresos_directos_por_concepto": _agrupar_ingresos_directos_por_concepto(
            ingresos
        ),
        "gastos_material": _serializar_gastos_material(gastos),
        "cajas": _serializar_cajas(inicio, fin),
        "operaciones_dispositivo": _serializar_operaciones_dispositivo(inicio, fin),
    }
