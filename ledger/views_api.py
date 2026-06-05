from django.db.models import Prefetch
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import (
    CanalCobro,
    ConceptoIngreso,
    EsquemaComision,
    MetodoPago,
    OrigenIngreso,
)


def _uuid_o_none(valor):
    return str(valor) if valor is not None else None


def _decimal_o_none(valor):
    return str(valor) if valor is not None else None


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
    }


@require_GET
def catalogos(request):
    generated_at = timezone.now().replace(microsecond=0)
    generated_at_iso = generated_at.isoformat().replace("+00:00", "Z")

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
