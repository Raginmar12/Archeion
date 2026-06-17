import json
from datetime import timezone as datetime_timezone
from decimal import Decimal

from django.db.models import Max, Prefetch, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .operations import OperationValidationError, procesar_operacion_chremata
from .models import (
    CajaFisica,
    CanalCobro,
    ConceptoIngreso,
    EsquemaComision,
    GastoMaterial,
    Ingreso,
    MetodoPago,
    PESOS_DECIMALES,
    OrigenIngreso,
)


def _uuid_o_none(valor):
    return str(valor) if valor is not None else None


def _decimal_o_none(valor):
    return str(valor) if valor is not None else None


def _datetime_utc_iso(valor):
    if valor is None:
        return None
    return (
        valor.astimezone(datetime_timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _generated_at_iso():
    return _datetime_utc_iso(timezone.now())


def _campo_schema(nombre, tipo, required=True, **extra):
    campo = {"name": nombre, "type": tipo, "required": required}
    campo.update(extra)
    return campo


def _chremata_catalogs_schema():
    return {
        "cajas_fisicas": {
            "identity": "public_id",
            "fields": [
                _campo_schema("public_id", "uuid"),
                _campo_schema("nombre", "string"),
                _campo_schema("descripcion", "string", required=False),
                _campo_schema("activa", "boolean"),
            ],
        },
        "metodos_pago": {
            "identity": "public_id",
            "fields": [
                _campo_schema("public_id", "uuid"),
                _campo_schema("nombre", "string"),
            ],
        },
        "canales_cobro": {
            "identity": "public_id",
            "fields": [
                _campo_schema("public_id", "uuid"),
                _campo_schema("nombre", "string"),
                _campo_schema(
                    "metodo_pago_public_id",
                    "uuid",
                    relation="metodos_pago.public_id",
                ),
                _campo_schema("metodo_pago", "string"),
                _campo_schema(
                    "esquema_comision_predeterminado_public_id",
                    "uuid",
                    required=False,
                    nullable=True,
                    relation="esquemas_comision.public_id",
                ),
            ],
        },
        "esquemas_comision": {
            "identity": "public_id",
            "fields": [
                _campo_schema("public_id", "uuid"),
                _campo_schema("nombre", "string"),
                _campo_schema("porcentaje_base", "decimal_string"),
                _campo_schema("cobra_iva", "boolean"),
                _campo_schema("porcentaje_iva", "decimal_string"),
                _campo_schema("porcentaje_total", "decimal_string"),
                _campo_schema(
                    "canales_cobro_public_ids",
                    "array_uuid",
                    relation="canales_cobro.public_id",
                ),
            ],
        },
        "conceptos_ingreso": {
            "identity": "public_id",
            "fields": [
                _campo_schema("public_id", "uuid"),
                _campo_schema("nombre", "string"),
                _campo_schema("descripcion", "string", required=False),
                _campo_schema("permite_material_adicional", "boolean"),
                _campo_schema("monto_material_sugerido", "money_string"),
            ],
        },
        "origenes_ingreso": {
            "identity": "public_id",
            "fields": [
                _campo_schema("public_id", "uuid"),
                _campo_schema("nombre", "string"),
                _campo_schema("descripcion", "string", required=False),
            ],
        },
    }


def _chremata_material_pool_schema():
    return {
        "endpoint": "/api/v1/chremata/material-pool/",
        "contract": "chremata.material_pool.v1",
        "schema_version": 1,
        "fields": {
            "contract": {"type": "string", "required": True},
            "app": {"type": "string", "required": True},
            "server_role": {"type": "string", "required": True},
            "schema_version": {"type": "int", "required": True},
            "generated_at": {"type": "datetime_utc_string", "required": True},
            "pool_material_actual": {"type": "decimal_string", "required": True},
            "total_gastos_material": {"type": "decimal_string", "required": True},
            "total_material_recuperado": {"type": "decimal_string", "required": True},
            "ultimo_gasto_material_fecha": {
                "type": "datetime_utc_string",
                "required": False,
                "nullable": True,
            },
            "ultimo_ingreso_con_material_fecha": {
                "type": "datetime_utc_string",
                "required": False,
                "nullable": True,
            },
        },
    }


def _chremata_tickets_schema():
    return {
        "entities": {
            "ticket": {
                "contract": "chremata.ticket.v1",
                "identity": "ticket_public_id",
                "allowed_states": [
                    "pendiente",
                    "cobrado",
                    "cancelado",
                    "abandonado",
                ],
                "fields": [
                    _campo_schema("ticket_public_id", "uuid"),
                    _campo_schema("fecha", "datetime_utc_string"),
                    _campo_schema("estado", "string"),
                    _campo_schema("nombre_referencia", "string", required=False),
                    _campo_schema(
                        "origen_ingreso_public_id",
                        "uuid",
                        relation="origenes_ingreso.public_id",
                    ),
                    _campo_schema("monto_total", "money_string"),
                    _campo_schema("monto_material_cobrado", "money_string"),
                    _campo_schema("monto_total_cobrado", "money_string"),
                    _campo_schema("notas", "string", required=False),
                    _campo_schema(
                        "lineas", "array", items_contract="chremata.ticket_line.v1"
                    ),
                ],
            },
            "ticket_linea": {
                "contract": "chremata.ticket_line.v1",
                "fields": [
                    _campo_schema(
                        "concepto_ingreso_public_id",
                        "uuid",
                        relation="conceptos_ingreso.public_id",
                    ),
                    _campo_schema("descripcion", "string", required=False),
                    _campo_schema("cantidad", "decimal_string"),
                    _campo_schema("monto_unitario", "money_string"),
                    _campo_schema("monto_total", "money_string"),
                    _campo_schema("monto_material_cobrado", "money_string"),
                    _campo_schema("orden", "int"),
                    _campo_schema("notas", "string", required=False),
                ],
            },
            "ticket_pago": {
                "contract": "chremata.ticket_payment.v1",
                "fields": [
                    _campo_schema(
                        "ticket_public_id", "uuid", relation="ticket.ticket_public_id"
                    ),
                    _campo_schema("fecha_cobro", "datetime_utc_string"),
                    _campo_schema(
                        "canal_cobro_public_id",
                        "uuid",
                        relation="canales_cobro.public_id",
                    ),
                    _campo_schema(
                        "esquema_comision_public_id",
                        "uuid",
                        required=False,
                        nullable=True,
                        relation="esquemas_comision.public_id",
                    ),
                    _campo_schema(
                        "concepto_ingreso_resumen_public_id",
                        "uuid",
                        relation="conceptos_ingreso.public_id",
                    ),
                    _campo_schema("notas", "string", required=False),
                ],
            },
        },
        "rules": {
            "ticket_pendiente_genera_ingreso": False,
            "ticket_cancelado_genera_ingreso": False,
            "ticket_abandonado_genera_ingreso": False,
            "solo_cobrar_ticket_genera_ticket_pago_e_ingreso": True,
            "material_pool_se_afecta_solo_con_ingreso_oficial": True,
            "metricas_por_concepto_salen_de_ticket_linea": True,
            "dinero_oficial_sale_de_ingreso": True,
            "nombre_referencia_es_referencia_operativa": True,
            "prohibe_datos_clinicos": [
                "diagnosticos",
                "recetas",
                "tratamientos",
                "expedientes",
            ],
        },
    }


def _ticket_operation_common(contract):
    return {
        "contract": contract,
        "method": "POST",
        "future_endpoint": "/api/v1/chremata/operations/",
        "idempotency_key": ["device_id", "device_entry_id"],
    }


def _chremata_operations_schema():
    operaciones = {
        "crear_ingreso": {
            "contract": "chremata.operation.crear_ingreso.v1",
            "method": "POST",
            "future_endpoint": "/api/v1/chremata/operations/",
            "idempotency_key": ["device_id", "device_entry_id"],
            "required_top_level_fields": [
                "operation",
                "operation_contract",
                "device_id",
                "device_entry_id",
                "payload",
            ],
            "payload_fields": [
                _campo_schema(
                    "concepto_ingreso_public_id",
                    "uuid",
                    relation="conceptos_ingreso.public_id",
                ),
                _campo_schema(
                    "origen_ingreso_public_id",
                    "uuid",
                    relation="origenes_ingreso.public_id",
                ),
                _campo_schema(
                    "canal_cobro_public_id",
                    "uuid",
                    relation="canales_cobro.public_id",
                ),
                _campo_schema(
                    "metodo_pago_public_id",
                    "uuid",
                    relation="metodos_pago.public_id",
                ),
                _campo_schema(
                    "esquema_comision_public_id",
                    "uuid",
                    required=False,
                    nullable=True,
                    relation="esquemas_comision.public_id",
                ),
                _campo_schema("monto_procedimiento", "money_string"),
                _campo_schema("monto_material_cobrado", "money_string"),
                _campo_schema("notas", "string", required=False),
            ],
            "server_authority": {
                "recalculates_commission": True,
                "recalculates_material_pool": True,
                "validates_catalog_public_ids": True,
                "device_calculations_are_audit_snapshot": True,
            },
        },
        "crear_gasto_material": {
            "contract": "chremata.operation.crear_gasto_material.v1",
            "method": "POST",
            "future_endpoint": "/api/v1/chremata/operations/",
            "idempotency_key": ["device_id", "device_entry_id"],
            "payload_fields": [
                _campo_schema("fecha", "datetime_utc_string"),
                _campo_schema("monto", "money_string"),
                _campo_schema(
                    "caja_public_id",
                    "uuid",
                    required=False,
                    nullable=True,
                    relation="caja_sesion.public_id",
                    compatibility="optional_temporarily",
                    future_client_rule="zephyros_should_send_when_cash_session_open",
                ),
                _campo_schema("descripcion", "string", required=False),
                _campo_schema("notas", "string", required=False),
            ],
            "server_authority": {
                "updates_material_pool": True,
                "device_values_are_input_not_authority": True,
            },
        },
    }

    operaciones["abrir_caja"] = {
        **_ticket_operation_common("chremata.operation.abrir_caja.v1"),
        "payload_fields": [
            _campo_schema("operation", "string"),
            _campo_schema("operation_contract", "string"),
            _campo_schema("device_id", "string"),
            _campo_schema("device_entry_id", "string"),
            _campo_schema("caja_public_id", "uuid"),
            _campo_schema(
                "caja_fisica_public_id",
                "uuid",
                required=False,
                nullable=True,
                relation="cajas_fisicas.public_id",
            ),
            _campo_schema("abierta_en", "datetime_utc_string"),
            _campo_schema("saldo_inicial_efectivo", "money_string"),
            _campo_schema("notas_apertura", "string", required=False),
        ],
        "server_authority": {
            "creates_caja_sesion": True,
            "requires_unique_open_session_by_device": True,
            "does_not_change_payments": True,
        },
    }
    operaciones["cerrar_caja"] = {
        **_ticket_operation_common("chremata.operation.cerrar_caja.v1"),
        "payload_fields": [
            _campo_schema("operation", "string"),
            _campo_schema("operation_contract", "string"),
            _campo_schema("device_id", "string"),
            _campo_schema("device_entry_id", "string"),
            _campo_schema("caja_public_id", "uuid", relation="caja_sesion.public_id"),
            _campo_schema("cerrada_en", "datetime_utc_string"),
            _campo_schema("efectivo_contado_cierre", "money_string"),
            _campo_schema("notas_cierre", "string", required=False),
        ],
        "server_authority": {
            "closes_caja_sesion": True,
            "snapshots_zero_totals_until_payments_are_linked": True,
            "does_not_change_payments": True,
        },
    }

    operaciones["crear_ticket"] = {
        **_ticket_operation_common("chremata.operation.crear_ticket.v1"),
        "payload_fields": [
            _campo_schema("operation", "string"),
            _campo_schema("operation_contract", "string"),
            _campo_schema("device_id", "string"),
            _campo_schema("device_entry_id", "string"),
            _campo_schema("ticket", "object", contract="chremata.ticket.v1"),
        ],
        "ticket_fields": _chremata_tickets_schema()["entities"]["ticket"]["fields"],
        "ticket_line_fields": _chremata_tickets_schema()["entities"]["ticket_linea"][
            "fields"
        ],
        "server_authority": {
            "creates_ingreso": False,
            "updates_material_pool": False,
            "validates_catalog_public_ids": True,
        },
    }
    operaciones["cobrar_ticket"] = {
        **_ticket_operation_common("chremata.operation.cobrar_ticket.v1"),
        "payload_fields": [
            _campo_schema("operation", "string"),
            _campo_schema("operation_contract", "string"),
            _campo_schema("device_id", "string"),
            _campo_schema("device_entry_id", "string"),
            _campo_schema(
                "ticket_public_id", "uuid", relation="ticket.ticket_public_id"
            ),
            _campo_schema("fecha_cobro", "datetime_utc_string"),
            _campo_schema(
                "canal_cobro_public_id",
                "uuid",
                relation="canales_cobro.public_id",
            ),
            _campo_schema(
                "esquema_comision_public_id",
                "uuid",
                required=False,
                nullable=True,
                relation="esquemas_comision.public_id",
            ),
            _campo_schema(
                "concepto_ingreso_resumen_public_id",
                "uuid",
                relation="conceptos_ingreso.public_id",
            ),
            _campo_schema(
                "caja_public_id",
                "uuid",
                required=False,
                nullable=True,
                relation="caja_sesion.public_id",
                compatibility="optional_temporarily",
                future_client_rule="zephyros_should_send_when_cash_session_open",
            ),
            _campo_schema("notas", "string", required=False),
        ],
        "server_authority": {
            "creates_ticket_pago": True,
            "creates_ingreso_oficial": True,
            "recalculates_commission": True,
            "updates_material_pool_through_ingreso": True,
            "validates_catalog_public_ids": True,
        },
    }
    operaciones["cancelar_ticket"] = {
        **_ticket_operation_common("chremata.operation.cancelar_ticket.v1"),
        "payload_fields": [
            _campo_schema("operation", "string"),
            _campo_schema("operation_contract", "string"),
            _campo_schema("device_id", "string"),
            _campo_schema("device_entry_id", "string"),
            _campo_schema(
                "ticket_public_id", "uuid", relation="ticket.ticket_public_id"
            ),
            _campo_schema("fecha_cancelacion", "datetime_utc_string"),
            _campo_schema("notas", "string", required=False),
        ],
        "server_authority": {
            "creates_ingreso": False,
            "updates_material_pool": False,
        },
    }
    operaciones["abandonar_ticket"] = {
        **_ticket_operation_common("chremata.operation.abandonar_ticket.v1"),
        "payload_fields": [
            _campo_schema("operation", "string"),
            _campo_schema("operation_contract", "string"),
            _campo_schema("device_id", "string"),
            _campo_schema("device_entry_id", "string"),
            _campo_schema(
                "ticket_public_id", "uuid", relation="ticket.ticket_public_id"
            ),
            _campo_schema("fecha_abandono", "datetime_utc_string"),
            _campo_schema("notas", "string", required=False),
        ],
        "server_authority": {
            "creates_ingreso": False,
            "updates_material_pool": False,
        },
    }

    return operaciones


def _serializar_caja_fisica(caja):
    return {
        "id": caja.id,
        "public_id": str(caja.public_id),
        "nombre": caja.nombre,
        "descripcion": caja.descripcion,
        "activa": caja.activa,
    }


def _serializar_metodo_pago(metodo):
    return {
        "id": metodo.id,
        "public_id": str(metodo.public_id),
        "nombre": metodo.nombre,
    }


def _serializar_canal_cobro(canal):
    esquema = canal.esquema_comision_predeterminado
    return {
        "id": canal.id,
        "public_id": str(canal.public_id),
        "nombre": canal.nombre,
        "metodo_pago_id": canal.metodo_pago_id,
        "metodo_pago_public_id": str(canal.metodo_pago.public_id),
        "metodo_pago": canal.metodo_pago.nombre,
        "esquema_comision_predeterminado_id": canal.esquema_comision_predeterminado_id,
        "esquema_comision_predeterminado_public_id": _uuid_o_none(
            esquema.public_id if esquema else None,
        ),
    }


def _serializar_esquema_comision(esquema):
    canales = esquema.canales_cobro_activos
    return {
        "id": esquema.id,
        "public_id": str(esquema.public_id),
        "nombre": esquema.nombre,
        "porcentaje_base": str(esquema.porcentaje_base),
        "cobra_iva": esquema.cobra_iva,
        "porcentaje_iva": str(esquema.porcentaje_iva),
        "porcentaje_total": str(esquema.porcentaje_total),
        "canales_cobro_ids": [canal.id for canal in canales],
        "canales_cobro_public_ids": [str(canal.public_id) for canal in canales],
    }


def _serializar_concepto_ingreso(concepto):
    return {
        "id": concepto.id,
        "public_id": str(concepto.public_id),
        "nombre": concepto.nombre,
        "descripcion": concepto.descripcion,
        "permite_material_adicional": concepto.permite_material_adicional,
        "monto_material_sugerido": _decimal_o_none(concepto.monto_material_sugerido),
    }


def _serializar_origen_ingreso(origen):
    return {
        "id": origen.id,
        "public_id": str(origen.public_id),
        "nombre": origen.nombre,
        "descripcion": origen.descripcion,
    }


def _material_pool_snapshot():
    total_gastos_material = GastoMaterial.objects.aggregate(
        total=Sum("monto"),
    )[
        "total"
    ] or Decimal("0.00")
    total_material_recuperado = Ingreso.objects.aggregate(
        total=Sum("material_recuperado"),
    )["total"] or Decimal("0.00")
    pool_material_actual = total_gastos_material - total_material_recuperado
    if pool_material_actual < Decimal("0.00"):
        pool_material_actual = Decimal("0.00")

    ultimo_gasto_material_fecha = GastoMaterial.objects.aggregate(
        fecha=Max("fecha"),
    )["fecha"]
    ultimo_ingreso_con_material_fecha = (
        Ingreso.objects.filter(monto_material_cobrado__gt=0)
        .aggregate(fecha=Max("fecha"))
        .get("fecha")
    )

    return {
        "pool_material_actual": pool_material_actual,
        "total_gastos_material": total_gastos_material,
        "total_material_recuperado": total_material_recuperado,
        "ultimo_gasto_material_fecha": ultimo_gasto_material_fecha,
        "ultimo_ingreso_con_material_fecha": ultimo_ingreso_con_material_fecha,
    }


@require_POST
def chremata_operations(request):
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "ok": False,
                "status": "failed",
                "error": {
                    "code": "invalid_json",
                    "message": "El cuerpo de la solicitud debe ser JSON válido.",
                },
            },
            status=400,
        )

    try:
        response, status_code = procesar_operacion_chremata(payload)
    except OperationValidationError as exc:
        return JsonResponse(
            {
                "ok": False,
                "status": exc.operation_status,
                "error": exc.to_error(),
            },
            status=exc.status_code,
        )

    return JsonResponse(response, status=status_code)


@require_GET
def material_pool(request):
    snapshot = _material_pool_snapshot()

    return JsonResponse(
        {
            "contract": "chremata.material_pool.v1",
            "app": "chremata",
            "server_role": "archeion",
            "schema_version": 1,
            "generated_at": _generated_at_iso(),
            "pool_material_actual": _decimal_o_none(
                snapshot["pool_material_actual"].quantize(PESOS_DECIMALES),
            ),
            "total_gastos_material": _decimal_o_none(
                snapshot["total_gastos_material"].quantize(PESOS_DECIMALES),
            ),
            "total_material_recuperado": _decimal_o_none(
                snapshot["total_material_recuperado"].quantize(PESOS_DECIMALES),
            ),
            "ultimo_gasto_material_fecha": _datetime_utc_iso(
                snapshot["ultimo_gasto_material_fecha"],
            ),
            "ultimo_ingreso_con_material_fecha": _datetime_utc_iso(
                snapshot["ultimo_ingreso_con_material_fecha"],
            ),
        },
    )


@require_GET
def catalogos(request):
    generated_at_iso = _generated_at_iso()

    cajas_fisicas = CajaFisica.objects.filter(activa=True).order_by("nombre", "id")
    metodos_pago = MetodoPago.objects.filter(activo=True).order_by("nombre", "id")
    canales_cobro = (
        CanalCobro.objects.filter(activo=True)
        .select_related(
            "metodo_pago",
            "esquema_comision_predeterminado",
        )
        .order_by("nombre", "id")
    )
    esquemas_comision = (
        EsquemaComision.objects.filter(activo=True)
        .prefetch_related(
            Prefetch(
                "canales_cobro",
                queryset=CanalCobro.objects.filter(activo=True).order_by(
                    "nombre",
                    "id",
                ),
                to_attr="canales_cobro_activos",
            ),
        )
        .order_by("nombre", "id")
    )
    conceptos_ingreso = ConceptoIngreso.objects.filter(activo=True).order_by(
        "nombre",
        "id",
    )
    origenes_ingreso = OrigenIngreso.objects.filter(activo=True).order_by(
        "nombre",
        "id",
    )

    return JsonResponse(
        {
            "schema_version": 1,
            "contract": "chremata.catalogs.v1",
            "app": "chremata",
            "snapshot_id": f"cat_{generated_at_iso}",
            "generated_at": generated_at_iso,
            "catalogs": {
                "cajas_fisicas": [
                    _serializar_caja_fisica(item) for item in cajas_fisicas
                ],
                "metodos_pago": [
                    _serializar_metodo_pago(item) for item in metodos_pago
                ],
                "canales_cobro": [
                    _serializar_canal_cobro(item) for item in canales_cobro
                ],
                "esquemas_comision": [
                    _serializar_esquema_comision(item) for item in esquemas_comision
                ],
                "conceptos_ingreso": [
                    _serializar_concepto_ingreso(item) for item in conceptos_ingreso
                ],
                "origenes_ingreso": [
                    _serializar_origen_ingreso(item) for item in origenes_ingreso
                ],
            },
        },
    )


@require_GET
def chremata_schema(request):
    return JsonResponse(
        {
            "schema_version": 1,
            "contract": "chremata.schema.v1",
            "app": "chremata",
            "server_role": "archeion",
            "generated_at": _generated_at_iso(),
            "compatible_with": {
                "catalogs": ["chremata.catalogs.v1"],
                "operations": [
                    "chremata.operation.crear_ingreso.v1",
                    "chremata.operation.crear_gasto_material.v1",
                    "chremata.operation.abrir_caja.v1",
                    "chremata.operation.cerrar_caja.v1",
                    "chremata.operation.crear_ticket.v1",
                    "chremata.operation.cobrar_ticket.v1",
                    "chremata.operation.cancelar_ticket.v1",
                    "chremata.operation.abandonar_ticket.v1",
                ],
                "clients": ["zephyros"],
            },
            "catalog_snapshot": {
                "endpoint": "/api/v1/catalogos/",
                "contract": "chremata.catalogs.v1",
                "current_schema_version": 1,
                "identity_field": "public_id",
                "contains_only_active_records": True,
                "decimals_are_strings": True,
                "uuids_are_strings": True,
                "nullable_fields_use_null": True,
            },
            "material_pool": _chremata_material_pool_schema(),
            "tickets": _chremata_tickets_schema(),
            "catalogs": _chremata_catalogs_schema(),
            "operations": _chremata_operations_schema(),
        },
    )
