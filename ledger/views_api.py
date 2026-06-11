from datetime import timezone as datetime_timezone
from decimal import Decimal

from django.db.models import Max, Prefetch, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import (
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


def _chremata_operations_schema():
    return {
        "crear_ingreso": {
            "contract": "chremata.operation.crear_ingreso.v1",
            "method": "POST",
            "future_endpoint": "/api/v1/chremata/operations/",
            "idempotency_key": ["device_id", "device_entry_id"],
            "required_top_level_fields": [
                "schema_version",
                "operation_type",
                "device_entry_id",
                "device_id",
                "catalog_snapshot_id",
                "catalog_snapshot_generated_at",
                "capturado_en_device",
                "device_timezone",
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
                _campo_schema("fecha", "datetime"),
                _campo_schema("monto", "money_string"),
                _campo_schema("descripcion", "string", required=False),
                _campo_schema("notas", "string", required=False),
            ],
            "server_authority": {
                "updates_material_pool": True,
                "device_values_are_input_not_authority": True,
            },
        },
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
            "catalogs": _chremata_catalogs_schema(),
            "operations": _chremata_operations_schema(),
        },
    )
