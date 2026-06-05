from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ledger", "0006_gastomaterial_conceptoingreso_incluye_material_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="conceptoingreso",
            old_name="incluye_material",
            new_name="permite_material_adicional",
        ),
        migrations.AlterField(
            model_name="conceptoingreso",
            name="permite_material_adicional",
            field=models.BooleanField(
                default=False,
                verbose_name="permite material adicional",
            ),
        ),
        migrations.AlterField(
            model_name="conceptoingreso",
            name="monto_material_sugerido",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=10,
                verbose_name="monto material sugerido",
            ),
        ),
    ]
