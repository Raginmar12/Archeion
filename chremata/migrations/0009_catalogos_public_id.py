import uuid

from django.db import migrations, models


CATALOGOS = (
    "MetodoPago",
    "CanalCobro",
    "EsquemaComision",
    "ConceptoIngreso",
    "OrigenIngreso",
)


def poblar_public_ids(apps, schema_editor):
    for nombre_modelo in CATALOGOS:
        modelo = apps.get_model("chremata", nombre_modelo)
        for objeto in modelo.objects.filter(public_id__isnull=True).iterator():
            objeto.public_id = uuid.uuid4()
            objeto.save(update_fields=["public_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("chremata", "0008_rename_monto_bruto_add_monto_total"),
    ]

    operations = [
        *[
            migrations.AddField(
                model_name=nombre_modelo.lower(),
                name="public_id",
                field=models.UUIDField(editable=False, null=True),
            )
            for nombre_modelo in CATALOGOS
        ],
        migrations.RunPython(poblar_public_ids, migrations.RunPython.noop),
        *[
            migrations.AlterField(
                model_name=nombre_modelo.lower(),
                name="public_id",
                field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
            )
            for nombre_modelo in CATALOGOS
        ],
    ]
