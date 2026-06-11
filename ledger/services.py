from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Ingreso, Ticket, TicketPago


def cobrar_ticket(
    *,
    ticket,
    fecha_cobro,
    canal_cobro,
    concepto_ingreso,
    esquema_comision=None,
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
            notas=notas_ingreso,
        )

        pago = TicketPago.objects.create(
            ticket=ticket_bloqueado,
            ingreso=ingreso,
            fecha=fecha_cobro,
            canal_cobro=canal_cobro,
            esquema_comision=ingreso.esquema_comision,
            concepto_ingreso=concepto_ingreso,
            notas=notas,
        )

        ticket_bloqueado.estado = Ticket.ESTADO_COBRADO
        ticket_bloqueado.save(update_fields=["estado", "actualizado_en"])

        return pago
