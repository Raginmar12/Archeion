from decimal import Decimal

from django.db import migrations, models
from django.db.models import F


def completar_monto_total(apps, schema_editor):
    Ingreso = apps.get_model("ledger", "Ingreso")
    Ingreso.objects.update(
        monto_total=F("monto_procedimiento") + F("monto_material_cobrado"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("ledger", "0007_rename_incluye_material_and_verbose_names"),
    ]

    operations = [
        migrations.RenameField(
            model_name="ingreso",
            old_name="monto_bruto",
            new_name="monto_procedimiento",
        ),
        migrations.AddField(
            model_name="ingreso",
            name="monto_total",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=10,
            ),
        ),
        migrations.RunPython(completar_monto_total, migrations.RunPython.noop),
    ]
