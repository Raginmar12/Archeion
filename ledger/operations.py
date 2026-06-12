import hashlib
import json
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from .models import (
    ConceptoIngreso,
    OperacionDispositivoChremata,
    OrigenIngreso,
    PESOS_DECIMALES,
    Ticket,
    TicketLinea,
)

CREAR_TICKET = "crear_ticket"
CREAR_TICKET_CONTRACT = "chremata.operation.crear_ticket.v1"


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
    if parsed.tzinfo is None or parsed.utcoffset() != datetime_timezone.utc.utcoffset(
        parsed
    ):
        raise OperationValidationError(
            "invalid_datetime",
            f"{field} debe incluir zona horaria UTC.",
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


def _validar_operacion_crear_ticket(payload):
    if payload["operation"] != CREAR_TICKET:
        raise OperationValidationError(
            "unsupported_operation",
            "Esta fase solo soporta operation=crear_ticket.",
            fields={"operation": "unsupported"},
            status_code=400,
        )
    if payload["operation_contract"] != CREAR_TICKET_CONTRACT:
        raise OperationValidationError(
            "invalid_operation_contract",
            "operation_contract no corresponde a crear_ticket v1.",
            fields={"operation_contract": "invalid"},
            status_code=400,
        )


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


def _procesar_payload_nuevo(payload):
    _validar_operacion_crear_ticket(payload)
    ticket, result = _handle_crear_ticket(payload)
    response = _respuesta_base(
        payload,
        OperacionDispositivoChremata.STATUS_PROCESSED,
        result=result,
    )
    return ticket, response


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
                ticket, response = _procesar_payload_nuevo(payload)
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
        operacion.procesado_en = timezone.now()
        operacion.save(
            update_fields=[
                "status",
                "response",
                "ticket",
                "procesado_en",
                "actualizado_en",
            ],
        )
        return response, 200
