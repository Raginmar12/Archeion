import hashlib
import json
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    CajaFisica,
    CajaSesion,
    CanalCobro,
    ConceptoIngreso,
    EsquemaComision,
    GastoMaterial,
    OperacionDispositivoChremata,
    OrigenIngreso,
    PESOS_DECIMALES,
    PORCENTAJE_DECIMALES,
    Ticket,
    TicketLinea,
)
from .services import abandonar_ticket, cancelar_ticket, cobrar_ticket

CREAR_TICKET = "crear_ticket"
CREAR_TICKET_CONTRACT = "chremata.operation.crear_ticket.v1"
COBRAR_TICKET = "cobrar_ticket"
COBRAR_TICKET_CONTRACT = "chremata.operation.cobrar_ticket.v1"
CANCELAR_TICKET = "cancelar_ticket"
CANCELAR_TICKET_CONTRACT = "chremata.operation.cancelar_ticket.v1"
ABANDONAR_TICKET = "abandonar_ticket"
ABANDONAR_TICKET_CONTRACT = "chremata.operation.abandonar_ticket.v1"
CREAR_GASTO_MATERIAL = "crear_gasto_material"
CREAR_GASTO_MATERIAL_CONTRACT = "chremata.operation.crear_gasto_material.v1"
ABRIR_CAJA = "abrir_caja"
ABRIR_CAJA_CONTRACT = "chremata.operation.abrir_caja.v1"
CERRAR_CAJA = "cerrar_caja"
CERRAR_CAJA_CONTRACT = "chremata.operation.cerrar_caja.v1"


class OperationValidationError(Exception):
    def __init__(
        self,
        code,
        message,
        *,
        fields=None,
        field=None,
        status_code=422,
        operation_status=OperacionDispositivoChremata.STATUS_FAILED,
    ):
        self.code = code
        self.message = message
        self.fields = fields
        self.field = field
        self.status_code = status_code
        self.operation_status = operation_status
        super().__init__(message)

    def to_error(self):
        error = {"code": self.code, "message": self.message}
        if self.field:
            error["field"] = self.field
        if self.fields:
            error["fields"] = self.fields
        return error


def calcular_payload_hash(payload):
    payload_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def error_response(code, message, fields=None, **extra):
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    error.update(extra)
    return {"ok": False, "status": "failed", "error": error}


def require_fields(data, fields):
    missing = {field: "required" for field in fields if field not in data}
    if missing:
        raise OperationValidationError(
            "invalid_payload",
            "Faltan campos requeridos.",
            fields=missing,
            status_code=400,
        )


def parse_uuid(value, field):
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise OperationValidationError(
            "invalid_uuid",
            f"{field} debe ser un UUID válido.",
            fields={field: "invalid_uuid"},
            status_code=400,
        ) from exc


def parse_decimal_string(value, field):
    if not isinstance(value, str):
        raise OperationValidationError(
            "invalid_decimal",
            f"{field} debe ser string decimal.",
            fields={field: "invalid_decimal_string"},
            status_code=400,
        )
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise OperationValidationError(
            "invalid_decimal",
            f"{field} debe ser decimal válido.",
            fields={field: "invalid_decimal_string"},
            status_code=400,
        ) from exc


def parse_money_string(value, field):
    return parse_decimal_string(value, field).quantize(
        PESOS_DECIMALES,
        rounding=ROUND_HALF_UP,
    )


def parse_datetime_utc_string(value, field):
    if not isinstance(value, str):
        raise OperationValidationError(
            "invalid_datetime",
            f"{field} debe ser datetime UTC string.",
            fields={field: "invalid_datetime_utc_string"},
            status_code=400,
        )
    iso_value = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_value)
    except ValueError as exc:
        raise OperationValidationError(
            "invalid_datetime",
            f"{field} debe ser datetime UTC string válido.",
            fields={field: "invalid_datetime_utc_string"},
            status_code=400,
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OperationValidationError(
            "invalid_datetime",
            f"{field} debe incluir zona horaria.",
            fields={field: "invalid_datetime_utc_string"},
            status_code=400,
        )
    return parsed.astimezone(datetime_timezone.utc)


def get_by_public_id(modelo, public_id, field):
    try:
        return modelo.objects.get(public_id=public_id)
    except modelo.DoesNotExist as exc:
        raise OperationValidationError(
            "reference_not_found",
            f"No existe {modelo.__name__} con ese public_id.",
            field=field,
            status_code=422,
        ) from exc


def _decimal_money_string(valor):
    return str((valor or Decimal("0.00")).quantize(PESOS_DECIMALES))


def _decimal_percentage_string(valor):
    return str((valor or Decimal("0.0000")).quantize(PORCENTAJE_DECIMALES))


def _datetime_utc_string(valor):
    return (
        valor.astimezone(datetime_timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _validation_error_to_operation_error(exc):
    if hasattr(exc, "message_dict"):
        fields = {campo: mensajes for campo, mensajes in exc.message_dict.items()}
        mensajes = [mensaje for mensajes in fields.values() for mensaje in mensajes]
    else:
        fields = {"__all__": exc.messages}
        mensajes = exc.messages
    message = mensajes[0] if mensajes else "La operación no pudo procesarse."
    return OperationValidationError(
        "business_validation_error",
        message,
        fields=fields,
        status_code=422,
    )


def _respuesta_base(payload, status, *, duplicate=False, result=None, error=None):
    response = {
        "ok": error is None,
        "operation": payload.get("operation"),
        "operation_contract": payload.get("operation_contract"),
        "device_id": payload.get("device_id"),
        "device_entry_id": payload.get("device_entry_id"),
        "status": status,
        "duplicate": duplicate,
    }
    if error is not None:
        response["error"] = error
    if result is not None:
        response["result"] = result
    return response


def _validar_campos_comunes(payload):
    if not isinstance(payload, dict):
        raise OperationValidationError(
            "invalid_payload",
            "El payload debe ser un objeto JSON.",
            status_code=400,
        )
    require_fields(
        payload, ["operation", "operation_contract", "device_id", "device_entry_id"]
    )
    for field in ["operation", "operation_contract", "device_id", "device_entry_id"]:
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise OperationValidationError(
                "invalid_payload",
                f"{field} debe ser string no vacío.",
                fields={field: "invalid_string"},
                status_code=400,
            )


def _validar_operacion_soportada(payload):
    contratos = {
        CREAR_TICKET: CREAR_TICKET_CONTRACT,
        COBRAR_TICKET: COBRAR_TICKET_CONTRACT,
        CANCELAR_TICKET: CANCELAR_TICKET_CONTRACT,
        ABANDONAR_TICKET: ABANDONAR_TICKET_CONTRACT,
        CREAR_GASTO_MATERIAL: CREAR_GASTO_MATERIAL_CONTRACT,
        ABRIR_CAJA: ABRIR_CAJA_CONTRACT,
        CERRAR_CAJA: CERRAR_CAJA_CONTRACT,
    }
    operation = payload["operation"]
    if operation not in contratos:
        raise OperationValidationError(
            "unsupported_operation",
            "Esta fase soporta crear_ticket, cobrar_ticket, cancelar_ticket, "
            "abandonar_ticket, crear_gasto_material, abrir_caja y cerrar_caja.",
            fields={"operation": "unsupported"},
            status_code=400,
        )
    if payload["operation_contract"] != contratos[operation]:
        raise OperationValidationError(
            "invalid_operation_contract",
            f"operation_contract no corresponde a {operation} v1.",
            fields={"operation_contract": "invalid"},
            status_code=400,
        )


def parse_caja_public_id(value):
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise OperationValidationError(
            "invalid_payload",
            "caja_public_id debe ser un UUID válido.",
            fields={"caja_public_id": "invalid_uuid"},
            status_code=400,
        ) from exc


def _obtener_caja_sesion_operacion(payload):
    if payload.get("caja_public_id") is None:
        return None

    caja_public_id = parse_caja_public_id(payload["caja_public_id"])
    try:
        caja = CajaSesion.objects.get(public_id=caja_public_id)
    except CajaSesion.DoesNotExist as exc:
        raise OperationValidationError(
            "missing_dependency",
            "No existe una sesión de caja con ese caja_public_id.",
            field="caja_public_id",
            status_code=422,
        ) from exc

    if caja.estado != CajaSesion.ESTADO_ABIERTA:
        raise OperationValidationError(
            "business_validation_error",
            "La sesión de caja debe estar abierta.",
            fields={"caja_public_id": ["La sesión de caja debe estar abierta."]},
            status_code=422,
        )

    if caja.device_id != payload["device_id"]:
        raise OperationValidationError(
            "business_validation_error",
            "La sesión de caja pertenece a otro dispositivo.",
            fields={"caja_public_id": ["La caja pertenece a otro dispositivo."]},
            status_code=422,
        )

    return caja


def _validar_money_no_negativo(valor, campo):
    monto = parse_money_string(valor, campo)
    if monto < Decimal("0.00"):
        raise OperationValidationError(
            "business_validation_error",
            f"{campo} debe ser mayor o igual que cero.",
            fields={campo: ["Debe ser mayor o igual que cero."]},
            status_code=422,
        )
    return monto


def _serializar_caja_fisica_operacion(caja_fisica):
    if caja_fisica is None:
        return None
    return {
        "public_id": str(caja_fisica.public_id),
        "nombre": caja_fisica.nombre,
    }


def _resultado_caja_abierta(caja):
    return {
        "caja_public_id": str(caja.public_id),
        "estado": caja.estado,
        "abierta_en": _datetime_utc_string(caja.abierta_en),
        "saldo_inicial_efectivo": _decimal_money_string(
            caja.saldo_inicial_efectivo,
        ),
        "caja_fisica": _serializar_caja_fisica_operacion(caja.caja_fisica),
    }


def _totales_caja_cero():
    return {
        "total_efectivo": Decimal("0.00"),
        "total_tarjeta": Decimal("0.00"),
        "total_transferencia": Decimal("0.00"),
        "total_bruto": Decimal("0.00"),
        "total_material_cobrado": Decimal("0.00"),
        "total_comisiones": Decimal("0.00"),
        "total_neto_estimado": Decimal("0.00"),
    }


def _totales_caja_cero_strings():
    return {
        campo: _decimal_money_string(valor)
        for campo, valor in _totales_caja_cero().items()
    }


def _resultado_caja_cerrada(caja):
    return {
        "caja_public_id": str(caja.public_id),
        "estado": caja.estado,
        "abierta_en": _datetime_utc_string(caja.abierta_en),
        "cerrada_en": _datetime_utc_string(caja.cerrada_en),
        "saldo_inicial_efectivo": _decimal_money_string(
            caja.saldo_inicial_efectivo,
        ),
        "efectivo_contado_cierre": _decimal_money_string(
            caja.efectivo_contado_cierre,
        ),
        "efectivo_esperado": _decimal_money_string(caja.efectivo_esperado),
        "diferencia_efectivo": _decimal_money_string(caja.diferencia_efectivo),
        **_totales_caja_cero_strings(),
    }


def _handle_abrir_caja(payload):
    require_fields(payload, ["caja_public_id", "abierta_en", "saldo_inicial_efectivo"])
    caja_public_id = parse_uuid(payload["caja_public_id"], "caja_public_id")
    abierta_en = parse_datetime_utc_string(payload["abierta_en"], "abierta_en")
    saldo_inicial_efectivo = _validar_money_no_negativo(
        payload["saldo_inicial_efectivo"],
        "saldo_inicial_efectivo",
    )

    notas_apertura = payload.get("notas_apertura", "")
    if not isinstance(notas_apertura, str):
        raise OperationValidationError(
            "invalid_payload",
            "notas_apertura debe ser string.",
            fields={"notas_apertura": "invalid_string"},
            status_code=400,
        )

    caja_fisica = None
    if payload.get("caja_fisica_public_id") is not None:
        caja_fisica_public_id = parse_uuid(
            payload["caja_fisica_public_id"],
            "caja_fisica_public_id",
        )
        caja_fisica = get_by_public_id(
            CajaFisica,
            caja_fisica_public_id,
            "caja_fisica_public_id",
        )
        if not caja_fisica.activa:
            raise OperationValidationError(
                "business_validation_error",
                "La caja física no está activa.",
                fields={"caja_fisica_public_id": ["La caja física no está activa."]},
                status_code=422,
            )

    if CajaSesion.objects.filter(public_id=caja_public_id).exists():
        raise OperationValidationError(
            "caja_public_id_conflict",
            "Ya existe una sesión de caja con ese caja_public_id.",
            fields={"caja_public_id": "already_exists"},
            status_code=409,
            operation_status=OperacionDispositivoChremata.STATUS_CONFLICT,
        )

    if CajaSesion.objects.filter(
        device_id=payload["device_id"],
        estado=CajaSesion.ESTADO_ABIERTA,
    ).exists():
        raise OperationValidationError(
            "caja_abierta_exists",
            "Ya existe una sesión de caja abierta para este dispositivo.",
            fields={"device_id": ["Ya existe una caja abierta para este dispositivo."]},
            status_code=422,
        )

    caja = CajaSesion.objects.create(
        public_id=caja_public_id,
        device_id=payload["device_id"],
        caja_fisica=caja_fisica,
        estado=CajaSesion.ESTADO_ABIERTA,
        abierta_en=abierta_en,
        saldo_inicial_efectivo=saldo_inicial_efectivo,
        notas_apertura=notas_apertura,
    )
    return caja, _resultado_caja_abierta(caja)


def _crear_resumen_snapshot_cierre(caja):
    result = _resultado_caja_cerrada(caja)
    return {
        "contract": "chremata.caja_sesion.cierre_snapshot.v1",
        "generated_at": _datetime_utc_string(timezone.now()),
        "caja": {
            "caja_public_id": result["caja_public_id"],
            "estado": result["estado"],
            "device_id": caja.device_id,
            "caja_fisica": _serializar_caja_fisica_operacion(caja.caja_fisica),
            "abierta_en": result["abierta_en"],
            "cerrada_en": result["cerrada_en"],
        },
        "totales": {
            campo: result[campo]
            for campo in _totales_caja_cero().keys()
        },
        "efectivo": {
            "saldo_inicial_efectivo": result["saldo_inicial_efectivo"],
            "efectivo_contado_cierre": result["efectivo_contado_cierre"],
            "efectivo_esperado": result["efectivo_esperado"],
            "diferencia_efectivo": result["diferencia_efectivo"],
        },
    }


def _handle_cerrar_caja(payload):
    require_fields(
        payload,
        ["caja_public_id", "cerrada_en", "efectivo_contado_cierre"],
    )
    caja_public_id = parse_uuid(payload["caja_public_id"], "caja_public_id")
    cerrada_en = parse_datetime_utc_string(payload["cerrada_en"], "cerrada_en")
    efectivo_contado_cierre = _validar_money_no_negativo(
        payload["efectivo_contado_cierre"],
        "efectivo_contado_cierre",
    )
    notas_cierre = payload.get("notas_cierre", "")
    if not isinstance(notas_cierre, str):
        raise OperationValidationError(
            "invalid_payload",
            "notas_cierre debe ser string.",
            fields={"notas_cierre": "invalid_string"},
            status_code=400,
        )

    caja = get_by_public_id(CajaSesion, caja_public_id, "caja_public_id")
    if caja.estado != CajaSesion.ESTADO_ABIERTA:
        raise OperationValidationError(
            "business_validation_error",
            "Solo se pueden cerrar sesiones de caja abiertas.",
            fields={"estado": ["Solo se pueden cerrar sesiones de caja abiertas."]},
            status_code=422,
        )
    if cerrada_en < caja.abierta_en:
        raise OperationValidationError(
            "business_validation_error",
            "La fecha de cierre debe ser mayor o igual que la fecha de apertura.",
            fields={
                "cerrada_en": [
                    "La fecha de cierre debe ser mayor o igual que la fecha de apertura."
                ]
            },
            status_code=422,
        )

    totales = _totales_caja_cero()
    efectivo_esperado = caja.saldo_inicial_efectivo
    diferencia_efectivo = (efectivo_contado_cierre - efectivo_esperado).quantize(
        PESOS_DECIMALES,
        rounding=ROUND_HALF_UP,
    )

    for campo, valor in totales.items():
        setattr(caja, campo, valor)
    caja.estado = CajaSesion.ESTADO_CERRADA
    caja.cerrada_en = cerrada_en
    caja.efectivo_contado_cierre = efectivo_contado_cierre
    caja.efectivo_esperado = efectivo_esperado
    caja.diferencia_efectivo = diferencia_efectivo
    caja.notas_cierre = notas_cierre
    caja.resumen_snapshot = _crear_resumen_snapshot_cierre(caja)
    caja.full_clean()
    caja.save(
        update_fields=[
            "estado",
            "cerrada_en",
            "efectivo_contado_cierre",
            "efectivo_esperado",
            "diferencia_efectivo",
            "total_efectivo",
            "total_tarjeta",
            "total_transferencia",
            "total_bruto",
            "total_material_cobrado",
            "total_comisiones",
            "total_neto_estimado",
            "notas_cierre",
            "resumen_snapshot",
            "actualizado_en",
        ],
    )
    return caja, _resultado_caja_cerrada(caja)


def _validar_linea(linea, indice):
    if not isinstance(linea, dict):
        raise OperationValidationError(
            "invalid_payload",
            "Cada línea debe ser un objeto JSON.",
            fields={f"lineas.{indice}": "invalid_object"},
            status_code=400,
        )
    require_fields(
        linea,
        [
            "concepto_ingreso_public_id",
            "cantidad",
            "monto_unitario",
            "monto_total",
            "monto_material_cobrado",
            "orden",
        ],
    )
    concepto_public_id = parse_uuid(
        linea["concepto_ingreso_public_id"],
        f"lineas.{indice}.concepto_ingreso_public_id",
    )
    concepto = get_by_public_id(
        ConceptoIngreso,
        concepto_public_id,
        f"lineas.{indice}.concepto_ingreso_public_id",
    )
    cantidad = parse_decimal_string(linea["cantidad"], f"lineas.{indice}.cantidad")
    monto_unitario = parse_money_string(
        linea["monto_unitario"],
        f"lineas.{indice}.monto_unitario",
    )
    monto_total = parse_money_string(
        linea["monto_total"], f"lineas.{indice}.monto_total"
    )
    monto_material_cobrado = parse_money_string(
        linea["monto_material_cobrado"],
        f"lineas.{indice}.monto_material_cobrado",
    )
    total_calculado = (cantidad * monto_unitario).quantize(
        PESOS_DECIMALES,
        rounding=ROUND_HALF_UP,
    )
    if monto_total != total_calculado:
        raise OperationValidationError(
            "line_total_mismatch",
            "El monto_total de la línea no coincide con cantidad * monto_unitario.",
            fields={f"lineas.{indice}.monto_total": "line_total_mismatch"},
            status_code=422,
        )
    if (
        monto_material_cobrado > Decimal("0.00")
        and not concepto.permite_material_adicional
    ):
        raise OperationValidationError(
            "business_validation_error",
            "El ticket no pudo crearse.",
            fields={
                f"lineas.{indice}.monto_material_cobrado": [
                    "Este concepto no permite cobrar material adicional."
                ],
            },
            status_code=422,
        )
    if not isinstance(linea["orden"], int):
        raise OperationValidationError(
            "invalid_payload",
            "orden debe ser entero.",
            fields={f"lineas.{indice}.orden": "invalid_int"},
            status_code=400,
        )
    return {
        "concepto": concepto,
        "descripcion": linea.get("descripcion", ""),
        "cantidad": cantidad,
        "monto_unitario": monto_unitario,
        "monto_total": monto_total,
        "monto_material_cobrado": monto_material_cobrado,
        "orden": linea["orden"],
        "notas": linea.get("notas", ""),
    }


def _handle_crear_ticket(payload):
    require_fields(payload, ["ticket"])
    ticket_payload = payload["ticket"]
    if not isinstance(ticket_payload, dict):
        raise OperationValidationError(
            "invalid_payload",
            "ticket debe ser un objeto JSON.",
            fields={"ticket": "invalid_object"},
            status_code=400,
        )
    require_fields(
        ticket_payload,
        [
            "ticket_public_id",
            "fecha",
            "estado",
            "origen_ingreso_public_id",
            "lineas",
        ],
    )
    ticket_public_id = parse_uuid(
        ticket_payload["ticket_public_id"], "ticket_public_id"
    )
    fecha = parse_datetime_utc_string(ticket_payload["fecha"], "fecha")
    if ticket_payload["estado"] != Ticket.ESTADO_PENDIENTE:
        raise OperationValidationError(
            "business_validation_error",
            "El ticket no pudo crearse.",
            fields={"estado": ["crear_ticket solo acepta estado pendiente."]},
            status_code=422,
        )
    origen_public_id = parse_uuid(
        ticket_payload["origen_ingreso_public_id"],
        "origen_ingreso_public_id",
    )
    origen = get_by_public_id(
        OrigenIngreso,
        origen_public_id,
        "origen_ingreso_public_id",
    )
    lineas_payload = ticket_payload["lineas"]
    if not isinstance(lineas_payload, list) or not lineas_payload:
        raise OperationValidationError(
            "invalid_payload",
            "ticket.lineas debe ser una lista no vacía.",
            fields={"lineas": "required_non_empty_list"},
            status_code=400,
        )
    if Ticket.objects.filter(public_id=ticket_public_id).exists():
        raise OperationValidationError(
            "ticket_public_id_conflict",
            "Ya existe un ticket con ese ticket_public_id.",
            fields={"ticket_public_id": "already_exists"},
            status_code=409,
            operation_status=OperacionDispositivoChremata.STATUS_CONFLICT,
        )
    lineas_validadas = [
        _validar_linea(linea, indice) for indice, linea in enumerate(lineas_payload)
    ]

    ticket = Ticket.objects.create(
        public_id=ticket_public_id,
        fecha=fecha,
        estado=Ticket.ESTADO_PENDIENTE,
        nombre_referencia=ticket_payload.get("nombre_referencia", ""),
        origen=origen,
        notas=ticket_payload.get("notas", ""),
    )
    for linea in lineas_validadas:
        TicketLinea.objects.create(ticket=ticket, **linea)
    ticket.refresh_from_db()

    return ticket, {
        "ticket_public_id": str(ticket.public_id),
        "ticket_estado": ticket.estado,
        "monto_total": str(ticket.monto_total),
        "monto_material_cobrado": str(ticket.monto_material_cobrado),
        "monto_total_cobrado": str(ticket.monto_total_cobrado),
    }


def _resultado_ticket_operativo(ticket, fecha, campo_fecha, *, incluir_nombre=False):
    result = {
        "ticket_public_id": str(ticket.public_id),
        "ticket_estado": ticket.estado,
        campo_fecha: _datetime_utc_string(fecha),
        "monto_total": _decimal_money_string(ticket.monto_total),
        "monto_material_cobrado": _decimal_money_string(
            ticket.monto_material_cobrado,
        ),
        "monto_total_cobrado": _decimal_money_string(ticket.monto_total_cobrado),
    }
    if incluir_nombre:
        result["nombre_referencia"] = ticket.nombre_referencia
    return result


def _handle_crear_gasto_material(payload):
    require_fields(payload, ["gasto_material"])
    gasto_payload = payload["gasto_material"]
    if not isinstance(gasto_payload, dict):
        raise OperationValidationError(
            "invalid_payload",
            "gasto_material debe ser un objeto JSON.",
            fields={"gasto_material": "invalid_object"},
            status_code=400,
        )
    require_fields(gasto_payload, ["fecha", "monto"])
    fecha = parse_datetime_utc_string(gasto_payload["fecha"], "gasto_material.fecha")
    monto = parse_money_string(gasto_payload["monto"], "gasto_material.monto")
    if monto <= Decimal("0.00"):
        raise OperationValidationError(
            "business_validation_error",
            "El monto del gasto de material debe ser mayor que cero.",
            fields={
                "monto": ["El monto del gasto de material debe ser mayor que cero."]
            },
            status_code=422,
        )

    descripcion = gasto_payload.get("descripcion", "")
    if not isinstance(descripcion, str):
        raise OperationValidationError(
            "invalid_payload",
            "descripcion debe ser string.",
            fields={"descripcion": "invalid_string"},
            status_code=400,
        )
    notas = gasto_payload.get("notas", "")
    if not isinstance(notas, str):
        raise OperationValidationError(
            "invalid_payload",
            "notas debe ser string.",
            fields={"notas": "invalid_string"},
            status_code=400,
        )

    caja_sesion = _obtener_caja_sesion_operacion(payload)
    gasto = GastoMaterial.objects.create(
        caja_sesion=caja_sesion,
        fecha=fecha,
        monto=monto,
        descripcion=descripcion,
        notas=notas,
    )
    return gasto, caja_sesion, {
        "fecha": _datetime_utc_string(gasto.fecha),
        "monto": _decimal_money_string(gasto.monto),
        "descripcion": gasto.descripcion,
    }


def _handle_cerrar_ticket_operativo(payload, *, operation, servicio, campo_fecha):
    require_fields(payload, ["ticket_public_id", campo_fecha])
    ticket_public_id = parse_uuid(payload["ticket_public_id"], "ticket_public_id")
    fecha = parse_datetime_utc_string(payload[campo_fecha], campo_fecha)
    notas = payload.get("notas", "")
    if not isinstance(notas, str):
        raise OperationValidationError(
            "invalid_payload",
            "notas debe ser string.",
            fields={"notas": "invalid_string"},
            status_code=400,
        )

    ticket = get_by_public_id(Ticket, ticket_public_id, "ticket_public_id")

    try:
        if operation == CANCELAR_TICKET:
            ticket = servicio(
                ticket=ticket,
                fecha_cancelacion=fecha,
                notas=notas,
            )
        else:
            ticket = servicio(
                ticket=ticket,
                fecha_abandono=fecha,
                notas=notas,
            )
    except ValidationError as exc:
        raise _validation_error_to_operation_error(exc) from exc

    ticket.refresh_from_db()
    return (
        ticket,
        None,
        None,
        _resultado_ticket_operativo(
            ticket,
            fecha,
            campo_fecha,
            incluir_nombre=operation == ABANDONAR_TICKET,
        ),
    )


def _handle_cobrar_ticket(payload):
    require_fields(
        payload,
        [
            "ticket_public_id",
            "fecha_cobro",
            "canal_cobro_public_id",
            "concepto_ingreso_resumen_public_id",
        ],
    )
    ticket_public_id = parse_uuid(payload["ticket_public_id"], "ticket_public_id")
    fecha_cobro = parse_datetime_utc_string(payload["fecha_cobro"], "fecha_cobro")
    canal_public_id = parse_uuid(
        payload["canal_cobro_public_id"],
        "canal_cobro_public_id",
    )
    concepto_public_id = parse_uuid(
        payload["concepto_ingreso_resumen_public_id"],
        "concepto_ingreso_resumen_public_id",
    )

    esquema_comision = None
    if payload.get("esquema_comision_public_id") is not None:
        esquema_public_id = parse_uuid(
            payload["esquema_comision_public_id"],
            "esquema_comision_public_id",
        )
        esquema_comision = get_by_public_id(
            EsquemaComision,
            esquema_public_id,
            "esquema_comision_public_id",
        )

    notas = payload.get("notas", "")
    if not isinstance(notas, str):
        raise OperationValidationError(
            "invalid_payload",
            "notas debe ser string.",
            fields={"notas": "invalid_string"},
            status_code=400,
        )

    caja_sesion = _obtener_caja_sesion_operacion(payload)
    ticket = get_by_public_id(Ticket, ticket_public_id, "ticket_public_id")
    canal_cobro = get_by_public_id(CanalCobro, canal_public_id, "canal_cobro_public_id")
    concepto_ingreso = get_by_public_id(
        ConceptoIngreso,
        concepto_public_id,
        "concepto_ingreso_resumen_public_id",
    )

    try:
        pago = cobrar_ticket(
            ticket=ticket,
            fecha_cobro=fecha_cobro,
            canal_cobro=canal_cobro,
            concepto_ingreso=concepto_ingreso,
            esquema_comision=esquema_comision,
            caja_sesion=caja_sesion,
            notas=notas,
        )
    except ValidationError as exc:
        raise _validation_error_to_operation_error(exc) from exc

    ticket = pago.ticket
    ingreso = pago.ingreso
    ticket.refresh_from_db()

    return (
        ticket,
        ingreso,
        pago,
        caja_sesion,
        {
            "ticket_public_id": str(ticket.public_id),
            "ticket_estado": ticket.estado,
            "fecha_cobro": _datetime_utc_string(ingreso.fecha),
            "monto_total": _decimal_money_string(ticket.monto_total),
            "monto_material_cobrado": _decimal_money_string(
                ticket.monto_material_cobrado,
            ),
            "monto_total_cobrado": _decimal_money_string(ingreso.monto_total),
            "porcentaje_comision_aplicado": _decimal_percentage_string(
                ingreso.porcentaje_comision_aplicado,
            ),
            "comision": _decimal_money_string(ingreso.comision),
            "monto_neto": _decimal_money_string(ingreso.monto_neto),
            "material_recuperado": _decimal_money_string(ingreso.material_recuperado),
            "material_excedente": _decimal_money_string(ingreso.material_excedente),
            "pool_material_antes": _decimal_money_string(ingreso.pool_material_antes),
            "pool_material_despues": _decimal_money_string(
                ingreso.pool_material_despues
            ),
        },
    )


def _procesar_payload_nuevo(payload):
    _validar_operacion_soportada(payload)
    gasto_material = None
    caja_sesion = None
    if payload["operation"] == ABRIR_CAJA:
        caja_sesion, result = _handle_abrir_caja(payload)
        ticket = None
        ingreso = None
        pago = None
    elif payload["operation"] == CERRAR_CAJA:
        caja_sesion, result = _handle_cerrar_caja(payload)
        ticket = None
        ingreso = None
        pago = None
    elif payload["operation"] == CREAR_TICKET:
        ticket, result = _handle_crear_ticket(payload)
        ingreso = None
        pago = None
    elif payload["operation"] == COBRAR_TICKET:
        ticket, ingreso, pago, caja_sesion, result = _handle_cobrar_ticket(payload)
    elif payload["operation"] == CANCELAR_TICKET:
        ticket, ingreso, pago, result = _handle_cerrar_ticket_operativo(
            payload,
            operation=CANCELAR_TICKET,
            servicio=cancelar_ticket,
            campo_fecha="fecha_cancelacion",
        )
    elif payload["operation"] == ABANDONAR_TICKET:
        ticket, ingreso, pago, result = _handle_cerrar_ticket_operativo(
            payload,
            operation=ABANDONAR_TICKET,
            servicio=abandonar_ticket,
            campo_fecha="fecha_abandono",
        )
    else:
        gasto_material, caja_sesion, result = _handle_crear_gasto_material(payload)
        ticket = None
        ingreso = None
        pago = None
    response = _respuesta_base(
        payload,
        OperacionDispositivoChremata.STATUS_PROCESSED,
        result=result,
    )
    return ticket, ingreso, pago, gasto_material, caja_sesion, response


def _respuesta_error(payload, exc, *, duplicate=False):
    return _respuesta_base(
        payload if isinstance(payload, dict) else {},
        exc.operation_status,
        duplicate=duplicate,
        error=exc.to_error(),
    )


def procesar_operacion_chremata(payload):
    _validar_campos_comunes(payload)
    payload_hash = calcular_payload_hash(payload)
    device_id = payload["device_id"]
    device_entry_id = payload["device_entry_id"]

    with transaction.atomic():
        operacion = (
            OperacionDispositivoChremata.objects.select_for_update()
            .filter(device_id=device_id, device_entry_id=device_entry_id)
            .first()
        )
        if operacion:
            if operacion.payload_hash != payload_hash:
                response = {
                    "ok": False,
                    "status": OperacionDispositivoChremata.STATUS_CONFLICT,
                    "device_id": device_id,
                    "device_entry_id": device_entry_id,
                    "error": {
                        "code": "payload_conflict",
                        "message": (
                            "Ya existe una operación con el mismo device_id y "
                            "device_entry_id pero payload diferente."
                        ),
                    },
                }
                return response, 409
            response = dict(operacion.response or {})
            response["duplicate"] = True
            status_code = 200
            if operacion.status == OperacionDispositivoChremata.STATUS_FAILED:
                status_code = 422
            if operacion.status == OperacionDispositivoChremata.STATUS_CONFLICT:
                status_code = 409
            return response, status_code

        operacion = OperacionDispositivoChremata.objects.create(
            device_id=device_id,
            device_entry_id=device_entry_id,
            operation=payload["operation"],
            operation_contract=payload["operation_contract"],
            payload=payload,
            payload_hash=payload_hash,
            status=OperacionDispositivoChremata.STATUS_RECEIVED,
        )

        try:
            with transaction.atomic():
                ticket, ingreso, pago, gasto_material, caja_sesion, response = (
                    _procesar_payload_nuevo(payload)
                )
        except OperationValidationError as exc:
            response = _respuesta_error(payload, exc)
            operacion.status = exc.operation_status
            operacion.error = response["error"]
            operacion.response = response
            operacion.procesado_en = timezone.now()
            operacion.save(
                update_fields=[
                    "status",
                    "error",
                    "response",
                    "procesado_en",
                    "actualizado_en",
                ],
            )
            return response, exc.status_code

        operacion.status = OperacionDispositivoChremata.STATUS_PROCESSED
        operacion.response = response
        operacion.ticket = ticket
        operacion.ingreso = ingreso
        operacion.ticket_pago = pago
        operacion.gasto_material = gasto_material
        operacion.caja_sesion = caja_sesion
        operacion.procesado_en = timezone.now()
        operacion.save(
            update_fields=[
                "status",
                "response",
                "ticket",
                "ingreso",
                "ticket_pago",
                "gasto_material",
                "caja_sesion",
                "procesado_en",
                "actualizado_en",
            ],
        )
        return response, 200
