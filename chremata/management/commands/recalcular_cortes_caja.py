from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from chremata.models import CajaSesion
from chremata.services import calcular_corte_caja


class Command(BaseCommand):
    help = "Recalcula cortes de cajas cerradas usando la fórmula vigente."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra antes/después sin modificar la base de datos.",
        )
        parser.add_argument(
            "--caja-public-id",
            help="Limita el recalculado a una CajaSesion cerrada específica.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        caja_public_id = options.get("caja_public_id")

        cajas = CajaSesion.objects.filter(estado=CajaSesion.ESTADO_CERRADA)
        if caja_public_id:
            cajas = cajas.filter(public_id=caja_public_id)
            if not cajas.exists():
                raise CommandError(
                    "No existe una CajaSesion cerrada con "
                    f"caja_public_id={caja_public_id}."
                )

        procesadas = 0
        actualizadas = 0

        with transaction.atomic():
            for caja in cajas.select_for_update().order_by("abierta_en", "id"):
                procesadas += 1
                snapshot_efectivo = caja.resumen_snapshot.get("efectivo", {})
                esperado_anterior = caja.efectivo_esperado
                diferencia_anterior = caja.diferencia_efectivo
                snapshot_esperado_anterior = snapshot_efectivo.get("efectivo_esperado")
                snapshot_diferencia_anterior = snapshot_efectivo.get(
                    "diferencia_efectivo"
                )

                corte = calcular_corte_caja(caja)
                efectivo = corte["efectivo"]
                esperado_nuevo = Decimal(efectivo["efectivo_esperado"])
                diferencia_nueva = Decimal(efectivo["diferencia_efectivo"])

                corte_para_comparar = dict(corte)
                if caja.resumen_snapshot.get("generated_at"):
                    corte_para_comparar["generated_at"] = caja.resumen_snapshot[
                        "generated_at"
                    ]
                cambio = (
                    esperado_anterior != esperado_nuevo
                    or diferencia_anterior != diferencia_nueva
                    or caja.resumen_snapshot != corte_para_comparar
                )
                if cambio:
                    actualizadas += 1

                self.stdout.write(f"Caja {caja.public_id}")
                self.stdout.write(f"  abierta_en: {caja.abierta_en.isoformat()}")
                self.stdout.write(f"  cerrada_en: {caja.cerrada_en.isoformat()}")
                self.stdout.write(
                    "  efectivo_esperado: "
                    f"{esperado_anterior} -> {esperado_nuevo}"
                )
                self.stdout.write(
                    "  diferencia_efectivo: "
                    f"{diferencia_anterior} -> {diferencia_nueva}"
                )
                self.stdout.write(
                    "  snapshot.efectivo_esperado: "
                    f"{snapshot_esperado_anterior} -> {efectivo['efectivo_esperado']}"
                )
                self.stdout.write(
                    "  snapshot.diferencia_efectivo: "
                    f"{snapshot_diferencia_anterior} -> "
                    f"{efectivo['diferencia_efectivo']}"
                )

                if not dry_run and cambio:
                    caja.efectivo_esperado = esperado_nuevo
                    caja.diferencia_efectivo = diferencia_nueva
                    caja.resumen_snapshot = corte_para_comparar
                    caja.full_clean()
                    caja.save(
                        update_fields=[
                            "efectivo_esperado",
                            "diferencia_efectivo",
                            "resumen_snapshot",
                            "actualizado_en",
                        ]
                    )

            if dry_run:
                self.stdout.write("DRY-RUN: no se modificó la base de datos.")
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Cajas procesadas: {procesadas}. Cajas con cambios: {actualizadas}."
            )
        )
