from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.core.management.base import BaseCommand

from chremata.models import ConceptoIngreso


CATALOGO_CONCEPTOS_INGRESO = [
    {
        "clave": "consulta-medica",
        "nombre": "Consulta médica",
        "precio_sugerido": Decimal("65.00"),
        "permite_material_adicional": False,
    },
    {
        "clave": "certificado-medico",
        "nombre": "Certificado médico",
        "precio_sugerido": Decimal("75.00"),
        "permite_material_adicional": False,
    },
    {
        "clave": "oximetria",
        "nombre": "Oximetría",
        "precio_sugerido": Decimal("30.00"),
        "permite_material_adicional": False,
    },
    {
        "clave": "toma-presion-arterial",
        "nombre": "Toma de presión arterial",
        "precio_sugerido": Decimal("30.00"),
        "permite_material_adicional": False,
    },
    {
        "clave": "aplicacion-inyeccion",
        "nombre": "Aplicación de inyección",
        "precio_sugerido": Decimal("30.00"),
        "permite_material_adicional": False,
    },
    {
        "clave": "prueba-detectar-niveles-azucar",
        "nombre": "Prueba para detectar niveles de azúcar",
        "precio_sugerido": Decimal("50.00"),
        "permite_material_adicional": False,
    },
    {
        "clave": "lavado-otico-cada-oido",
        "nombre": "Lavado ótico, cada oído",
        "precio_sugerido": Decimal("70.00"),
        "permite_material_adicional": True,
    },
    {
        "clave": "retiro-puntos",
        "nombre": "Retiro de puntos",
        "precio_sugerido": Decimal("70.00"),
        "permite_material_adicional": True,
        "preservar_monto_material_sugerido": True,
    },
    {
        "clave": "retiro-sondas",
        "nombre": "Retiro de sondas",
        "precio_sugerido": Decimal("70.00"),
        "permite_material_adicional": True,
    },
    {
        "clave": "extraccion-una-enterrada",
        "nombre": "Extracción de uña enterrada",
        "precio_sugerido": Decimal("70.00"),
        "permite_material_adicional": True,
    },
    {
        "clave": "nebulizaciones",
        "nombre": "Nebulizaciones",
        "precio_sugerido": Decimal("80.00"),
        "permite_material_adicional": True,
    },
    {
        "clave": "curacion",
        "nombre": "Curación",
        "precio_sugerido": Decimal("70.00"),
        "permite_material_adicional": True,
        "preservar_monto_material_sugerido": True,
    },
    {
        "clave": "sutura",
        "nombre": "Sutura",
        "precio_sugerido": Decimal("70.00"),
        "permite_material_adicional": True,
    },
    {
        "clave": "peso-talla-imc",
        "nombre": "Peso, talla, IMC",
        "precio_sugerido": Decimal("30.00"),
        "permite_material_adicional": False,
    },
    {
        "clave": "extraccion-cuerpo-extrano",
        "nombre": "Extracción de cuerpo extraño",
        "precio_sugerido": Decimal("120.00"),
        "permite_material_adicional": True,
    },
    {
        "clave": "lavado-nasal",
        "nombre": "Lavado nasal",
        "precio_sugerido": Decimal("120.00"),
        "permite_material_adicional": True,
    },
    {
        "clave": "retiro-verrugas",
        "nombre": "Retiro de verrugas",
        "precio_sugerido": Decimal("120.00"),
        "permite_material_adicional": True,
    },
    {
        "clave": "colocacion-retiro-implante",
        "nombre": "Colocación y retiro de implante",
        "precio_sugerido": Decimal("220.00"),
        "permite_material_adicional": True,
    },
    {
        "clave": "reseccion-lipoma",
        "nombre": "Resección de lipoma",
        "precio_sugerido": Decimal("220.00"),
        "permite_material_adicional": True,
    },
    {
        "clave": "perforacion-colocacion-arete",
        "nombre": "Perforación para colocación de arete",
        "precio_sugerido": Decimal("70.00"),
        "permite_material_adicional": True,
    },
    {
        "clave": "otro",
        "nombre": "Otro",
        "precio_sugerido": Decimal("0.00"),
        "permite_material_adicional": True,
    },
]

CONCEPTOS_OBSOLETOS = [
    "Control del niño sano",
    "Control de embarazo",
    "Planificación familiar",
]


def calcular_public_id_concepto(clave):
    return uuid5(NAMESPACE_URL, f"archeion/chremata/conceptos/{clave}")


class Command(BaseCommand):
    help = "Carga de forma idempotente los catálogos iniciales de Chremata."

    def handle(self, *args, **options):
        creados = 0
        actualizados = 0

        for concepto in CATALOGO_CONCEPTOS_INGRESO:
            public_id = calcular_public_id_concepto(concepto["clave"])
            monto_material_sugerido = Decimal("0.00")

            existente = ConceptoIngreso.objects.filter(public_id=public_id).first()
            if existente is None:
                existente = ConceptoIngreso.objects.filter(
                    nombre=concepto["nombre"],
                ).first()
                if existente is not None:
                    existente.public_id = public_id
                    existente.save(update_fields=["public_id"])

            if existente and concepto.get("preservar_monto_material_sugerido"):
                monto_material_sugerido = existente.monto_material_sugerido

            descripcion = (
                f"Precio sugerido en Zephyros: {concepto['precio_sugerido']:.2f}."
            )
            if concepto["nombre"] == "Otro":
                descripcion = "Captura manual de concepto y monto desde Zephyros."

            _, creado = ConceptoIngreso.objects.update_or_create(
                public_id=public_id,
                defaults={
                    "nombre": concepto["nombre"],
                    "descripcion": descripcion,
                    "permite_material_adicional": concepto["permite_material_adicional"],
                    "monto_material_sugerido": monto_material_sugerido,
                    "activo": True,
                },
            )
            if creado:
                creados += 1
            else:
                actualizados += 1

        desactivados = ConceptoIngreso.objects.filter(
            nombre__in=CONCEPTOS_OBSOLETOS,
            activo=True,
        ).update(activo=False)

        self.stdout.write(
            self.style.SUCCESS(
                "Catálogo de conceptos de Chremata actualizado: "
                f"{creados} creados, {actualizados} actualizados, "
                f"{desactivados} obsoletos desactivados."
            )
        )
