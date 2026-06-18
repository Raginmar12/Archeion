from datetime import timezone as datetime_timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .models import (
    CajaSesion,
    GastoMaterial,
    Ingreso,
    PESOS_DECIMALES,
    Ticket,
    TicketLinea,
    TicketPago,
)


def _money(valor):
    return str((valor or Decimal("0.00")).quantize(PESOS_DECIMALES))


def _datetime_utc(valor):
    if valor is None:
        return None
    return (
        valor.astimezone(datetime_timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _sumar(queryset, campo):
    return (queryset.aggregate(total=Sum(campo))["total"] or Decimal("0.00")).quantize(
        PESOS_DECIMALES
    )


def _serializar_caja(caja_sesion):
    caja_fisica = None
    if caja_sesion.caja_fisica_id:
        caja_fisica = {
            "public_id": str(caja_sesion.caja_fisica.public_id),
            "nombre": caja_sesion.caja_fisica.nombre,
        }
    origen_ingreso = None
    if caja_sesion.origen_ingreso_id:
        origen_ingreso = {
            "public_id": str(caja_sesion.origen_ingreso.public_id),
            "nombre": caja_sesion.origen_ingreso.nombre,
        }
    return {
        "caja_public_id": str(caja_sesion.public_id),
        "estado": caja_sesion.estado,
        "device_id": caja_sesion.device_id,
        "caja_fisica": caja_fisica,
        "origen_ingreso": origen_ingreso,
        "abierta_en": _datetime_utc(caja_sesion.abierta_en),
        "cerrada_en": _datetime_utc(caja_sesion.cerrada_en),
    }


def _intervalo_caja(caja_sesion):
    fin = caja_sesion.cerrada_en or timezone.now()
    return caja_sesion.abierta_en, fin


def calcular_corte_caja(caja_sesion):
    """Calcula el corte oficial de una sesión de caja Chremata."""

    ingresos = Ingreso.objects.filter(caja_sesion=caja_sesion).select_related(
        "canal_cobro",
        "canal_cobro__metodo_pago",
    )
    pagos = TicketPago.objects.filter(caja_sesion=caja_sesion).select_related(
        "ticket",
        "canal_cobro",
        "canal_cobro__metodo_pago",
    )

    total_bruto = _sumar(ingresos, "monto_total")
    total_material_cobrado = _sumar(ingresos, "monto_material_cobrado")
    total_comisiones = _sumar(ingresos, "comision")
    total_neto_estimado = _sumar(ingresos, "monto_neto")

    totales_metodo = {}
    for ingreso in ingresos:
        metodo = ingreso.canal_cobro.metodo_pago
        datos = totales_metodo.setdefault(
            metodo.pk,
            {
                "metodo_pago_public_id": str(metodo.public_id),
                "metodo_pago": metodo.nombre,
                "cantidad": 0,
                "total_bruto": Decimal("0.00"),
                "total_comisiones": Decimal("0.00"),
                "total_neto_estimado": Decimal("0.00"),
            },
        )
        datos["cantidad"] += 1
        datos["total_bruto"] += ingreso.monto_total
        datos["total_comisiones"] += ingreso.comision
        datos["total_neto_estimado"] += ingreso.monto_neto

    totales_canal = {}
    for ingreso in ingresos:
        canal = ingreso.canal_cobro
        datos = totales_canal.setdefault(
            canal.pk,
            {
                "canal_cobro_public_id": str(canal.public_id),
                "canal_cobro": canal.nombre,
                "metodo_pago": canal.metodo_pago.nombre,
                "cantidad": 0,
                "total_bruto": Decimal("0.00"),
                "total_comisiones": Decimal("0.00"),
                "total_neto_estimado": Decimal("0.00"),
            },
        )
        datos["cantidad"] += 1
        datos["total_bruto"] += ingreso.monto_total
        datos["total_comisiones"] += ingreso.comision
        datos["total_neto_estimado"] += ingreso.monto_neto

    def serializar_totales(items):
        serializados = []
        for item in items:
            serializado = dict(item)
            for campo in ("total_bruto", "total_comisiones", "total_neto_estimado"):
                serializado[campo] = _money(serializado[campo])
            serializados.append(serializado)
        return serializados

    total_efectivo = sum(
        (
            item["total_bruto"]
            for item in totales_metodo.values()
            if item["metodo_pago"].lower() == "efectivo"
        ),
        Decimal("0.00"),
    ).quantize(PESOS_DECIMALES)
    total_tarjeta = sum(
        (
            item["total_bruto"]
            for item in totales_metodo.values()
            if item["metodo_pago"].lower() == "tarjeta"
        ),
        Decimal("0.00"),
    ).quantize(PESOS_DECIMALES)
    total_transferencia = sum(
        (
            item["total_bruto"]
            for item in totales_metodo.values()
            if item["metodo_pago"].lower() == "transferencia"
        ),
        Decimal("0.00"),
    ).quantize(PESOS_DECIMALES)

    lineas = TicketLinea.objects.filter(ticket__pago__caja_sesion=caja_sesion)
    conceptos = lineas.values(
        "concepto__public_id",
        "concepto__nombre",
    ).annotate(
        cantidad_total=Sum("cantidad"),
        lineas=Count("id"),
        total=Sum("monto_total"),
        material_cobrado=Sum("monto_material_cobrado"),
    ).order_by("concepto__nombre")
    totales_por_concepto = [
        {
            "concepto_ingreso_public_id": str(item["concepto__public_id"]),
            "concepto": item["concepto__nombre"],
            "cantidad_total": str(item["cantidad_total"] or Decimal("0.00")),
            "lineas": item["lineas"],
            "total": _money(item["total"]),
            "material_cobrado": _money(item["material_cobrado"]),
        }
        for item in conceptos
    ]

    gastos = GastoMaterial.objects.filter(caja_sesion=caja_sesion).order_by("fecha", "id")
    total_gastos_material = _sumar(gastos, "monto")
    gastos_material = {
        "cantidad": gastos.count(),
        "total_gastos_material": _money(total_gastos_material),
        "detalle": [
            {
                "fecha": _datetime_utc(gasto.fecha),
                "monto": _money(gasto.monto),
                "descripcion": gasto.descripcion,
                "notas": gasto.notas,
            }
            for gasto in gastos
        ],
    }

    efectivo_esperado = (
        caja_sesion.saldo_inicial_efectivo + total_efectivo - total_gastos_material
    ).quantize(PESOS_DECIMALES)
    diferencia_efectivo = None
    if caja_sesion.efectivo_contado_cierre is not None:
        diferencia_efectivo = (
            caja_sesion.efectivo_contado_cierre - efectivo_esperado
        ).quantize(PESOS_DECIMALES)

    inicio, fin = _intervalo_caja(caja_sesion)
    tickets_creados = Ticket.objects.filter(fecha__gte=inicio, fecha__lte=fin)

    return {
        "contract": "chremata.corte_caja.v1",
        "generated_at": _datetime_utc(timezone.now()),
        "caja": _serializar_caja(caja_sesion),
        "efectivo": {
            "saldo_inicial_efectivo": _money(caja_sesion.saldo_inicial_efectivo),
            "total_efectivo": _money(total_efectivo),
            "efectivo_esperado": _money(efectivo_esperado),
            "efectivo_contado_cierre": _money(caja_sesion.efectivo_contado_cierre)
            if caja_sesion.efectivo_contado_cierre is not None
            else None,
            "diferencia_efectivo": _money(diferencia_efectivo)
            if diferencia_efectivo is not None
            else None,
        },
        "totales": {
            "total_bruto": _money(total_bruto),
            "total_efectivo": _money(total_efectivo),
            "total_tarjeta": _money(total_tarjeta),
            "total_transferencia": _money(total_transferencia),
            "total_material_cobrado": _money(total_material_cobrado),
            "total_comisiones": _money(total_comisiones),
            "total_neto_estimado": _money(total_neto_estimado),
        },
        "totales_por_metodo": serializar_totales(
            sorted(totales_metodo.values(), key=lambda item: item["metodo_pago"])
        ),
        "totales_por_canal": serializar_totales(
            sorted(totales_canal.values(), key=lambda item: item["canal_cobro"])
        ),
        "totales_por_concepto": totales_por_concepto,
        "gastos_material": gastos_material,
        "tickets": {
            "tickets_cobrados": pagos.count(),
            "tickets_pendientes_creados_durante_caja": tickets_creados.filter(
                estado=Ticket.ESTADO_PENDIENTE
            ).count(),
            "tickets_cancelados_creados_durante_caja": tickets_creados.filter(
                estado=Ticket.ESTADO_CANCELADO
            ).count(),
            "tickets_abandonados_creados_durante_caja": tickets_creados.filter(
                estado=Ticket.ESTADO_ABANDONADO
            ).count(),
        },
    }


def cobrar_ticket(
    *,
    ticket,
    fecha_cobro,
    canal_cobro,
    concepto_ingreso,
    esquema_comision=None,
    caja_sesion=None,
    notas="",
):
    """Cobra un ticket pendiente generando un TicketPago y un Ingreso oficial."""

    with transaction.atomic():
        ticket_bloqueado = (
            Ticket.objects.select_for_update()
            .select_related("origen")
            .get(pk=ticket.pk)
        )

        if ticket_bloqueado.estado != Ticket.ESTADO_PENDIENTE:
            raise ValidationError(
                {"estado": "Solo se pueden cobrar tickets pendientes."},
            )

        if not ticket_bloqueado.lineas.exists():
            raise ValidationError(
                {"lineas": "No se puede cobrar un ticket sin líneas."},
            )

        if TicketPago.objects.filter(ticket=ticket_bloqueado).exists():
            raise ValidationError(
                {"ticket": "Este ticket ya tiene un pago registrado."},
            )

        ticket_bloqueado.recalcular_totales()

        if (
            ticket_bloqueado.monto_material_cobrado > 0
            and not concepto_ingreso.permite_material_adicional
        ):
            raise ValidationError(
                {
                    "concepto_ingreso": (
                        "El concepto resumen debe permitir material adicional "
                        "cuando el ticket tiene material cobrado."
                    ),
                },
            )

        notas_ingreso = f"Ingreso generado desde ticket {ticket_bloqueado.public_id}."
        if notas:
            notas_ingreso = f"{notas_ingreso}\n\n{notas}"

        ingreso = Ingreso.objects.create(
            fecha=fecha_cobro,
            monto_procedimiento=ticket_bloqueado.monto_total,
            monto_material_cobrado=ticket_bloqueado.monto_material_cobrado,
            concepto=concepto_ingreso,
            canal_cobro=canal_cobro,
            esquema_comision=esquema_comision,
            origen=ticket_bloqueado.origen,
            caja_sesion=caja_sesion,
            notas=notas_ingreso,
        )

        pago = TicketPago.objects.create(
            ticket=ticket_bloqueado,
            ingreso=ingreso,
            fecha=fecha_cobro,
            canal_cobro=canal_cobro,
            esquema_comision=ingreso.esquema_comision,
            concepto_ingreso=concepto_ingreso,
            caja_sesion=caja_sesion,
            notas=notas,
        )

        ticket_bloqueado.estado = Ticket.ESTADO_COBRADO
        ticket_bloqueado.save(update_fields=["estado", "actualizado_en"])

        return pago


def _anexar_nota_operativa(notas_actuales, *, etiqueta, fecha, notas):
    fecha_iso = fecha.astimezone().replace(microsecond=0).isoformat()
    nota_operativa = f"{etiqueta} el {fecha_iso}."
    if notas:
        nota_operativa = f"{nota_operativa}\n{notas}"
    if notas_actuales:
        return f"{notas_actuales}\n\n{nota_operativa}"
    return nota_operativa


def _cambiar_estado_ticket_operativo(
    *, ticket, nuevo_estado, fecha, etiqueta, notas=""
):
    with transaction.atomic():
        ticket_bloqueado = Ticket.objects.select_for_update().get(pk=ticket.pk)

        if ticket_bloqueado.estado != Ticket.ESTADO_PENDIENTE:
            raise ValidationError(
                {"estado": "Solo se pueden modificar tickets pendientes."},
            )

        ticket_bloqueado.estado = nuevo_estado
        ticket_bloqueado.notas = _anexar_nota_operativa(
            ticket_bloqueado.notas,
            etiqueta=etiqueta,
            fecha=fecha,
            notas=notas,
        )
        ticket_bloqueado.save(update_fields=["estado", "notas", "actualizado_en"])
        return ticket_bloqueado


def cancelar_ticket(*, ticket, fecha_cancelacion, notas=""):
    """Cancela un ticket pendiente sin afectar Ingreso, TicketPago ni material pool."""

    return _cambiar_estado_ticket_operativo(
        ticket=ticket,
        nuevo_estado=Ticket.ESTADO_CANCELADO,
        fecha=fecha_cancelacion,
        etiqueta="Ticket cancelado",
        notas=notas,
    )


def abandonar_ticket(*, ticket, fecha_abandono, notas=""):
    """Marca un ticket pendiente como abandonado sin afectar registros oficiales."""

    return _cambiar_estado_ticket_operativo(
        ticket=ticket,
        nuevo_estado=Ticket.ESTADO_ABANDONADO,
        fecha=fecha_abandono,
        etiqueta="Ticket abandonado",
        notas=notas,
    )
