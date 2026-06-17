from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from chremata.models import (
    CajaFisica,
    CajaSesion,
    CanalCobro,
    ConceptoIngreso,
    EsquemaComision,
    GastoMaterial,
    Ingreso,
    MetodoPago,
    OperacionDispositivoChremata,
    OrigenIngreso,
    Ticket,
    TicketLinea,
    TicketPago,
)


CAJAS_FISICAS = [
    {
        "clave": "caja-principal",
        "nombre": "Caja principal",
        "descripcion": "Caja física principal de efectivo.",
    },
]

METODOS_PAGO = [
    {"clave": "efectivo", "nombre": "Efectivo"},
    {"clave": "tarjeta", "nombre": "Tarjeta"},
    {"clave": "transferencia", "nombre": "Transferencia"},
]

ESQUEMAS_COMISION = [
    {
        "clave": "sin-comision",
        "nombre": "Sin comisión",
        "porcentaje_base": Decimal("0.00"),
        "cobra_iva": False,
        "porcentaje_iva": Decimal("0.00"),
    },
    {
        "clave": "mercado-pago-3-5-iva",
        "nombre": "Mercado Pago 3.5% + IVA",
        "porcentaje_base": Decimal("3.50"),
        "cobra_iva": True,
        "porcentaje_iva": Decimal("16.00"),
    },
]

CANALES_COBRO = [
    {
        "clave": "efectivo-en-caja",
        "nombre": "Efectivo en caja",
        "metodo_pago": "Efectivo",
        "esquema_comision": "Sin comisión",
    },
    {
        "clave": "spei",
        "nombre": "SPEI",
        "metodo_pago": "Transferencia",
        "esquema_comision": "Sin comisión",
    },
    {
        "clave": "tap-mp",
        "nombre": "Tap (MP)",
        "metodo_pago": "Tarjeta",
        "esquema_comision": "Mercado Pago 3.5% + IVA",
    },
    {
        "clave": "point-air-mp",
        "nombre": "Point Air (MP)",
        "metodo_pago": "Tarjeta",
        "esquema_comision": "Mercado Pago 3.5% + IVA",
    },
]

ORIGENES_INGRESO = [
    {"clave": "similares", "nombre": "Similares"},
    {"clave": "metabocare", "nombre": "MetaboCare"},
]

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

MODELOS_CHREMATA_BASE_LIMPIA = [
    CajaFisica,
    CajaSesion,
    MetodoPago,
    CanalCobro,
    EsquemaComision,
    ConceptoIngreso,
    OrigenIngreso,
    Ingreso,
    GastoMaterial,
    Ticket,
    TicketLinea,
    TicketPago,
    OperacionDispositivoChremata,
]


def calcular_public_id(categoria, clave):
    return uuid5(NAMESPACE_URL, f"archeion/chremata/{categoria}/{clave}")


def calcular_public_id_concepto(clave):
    return calcular_public_id("conceptos", clave)


def descripcion_precio_sugerido(concepto):
    if concepto["nombre"] == "Otro":
        return "Captura manual de concepto y monto desde Zephyros."
    return f"Precio sugerido en Zephyros: {concepto['precio_sugerido']:.2f}."


class Command(BaseCommand):
    help = "Carga los catálogos iniciales de Chremata en una base limpia."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Valida base limpia y muestra el resumen sin crear registros.",
        )

    def handle(self, *args, **options):
        self._validar_base_limpia()

        resumen = {
            "cajas_fisicas": len(CAJAS_FISICAS),
            "metodos_pago": len(METODOS_PAGO),
            "esquemas_comision": len(ESQUEMAS_COMISION),
            "canales_cobro": len(CANALES_COBRO),
            "origenes_ingreso": len(ORIGENES_INGRESO),
            "conceptos_ingreso": len(CATALOGO_CONCEPTOS_INGRESO),
        }

        if options["dry_run"]:
            self._escribir_resumen("Dry-run: se crearían", resumen)
            return

        with transaction.atomic():
            self._crear_catalogos()

        self._escribir_resumen("Catálogos iniciales de Chremata creados", resumen)

    def _validar_base_limpia(self):
        modelos_con_registros = []
        for modelo in MODELOS_CHREMATA_BASE_LIMPIA:
            total = modelo.objects.count()
            if total:
                modelos_con_registros.append(f"{modelo.__name__}={total}")

        if modelos_con_registros:
            detalle = ", ".join(modelos_con_registros)
            raise CommandError(
                "seed_chremata_catalogs solo puede ejecutarse sobre una base "
                f"limpia. Modelos con registros: {detalle}."
            )

    def _crear_catalogos(self):
        for caja in CAJAS_FISICAS:
            CajaFisica.objects.create(
                public_id=calcular_public_id("cajas-fisicas", caja["clave"]),
                nombre=caja["nombre"],
                descripcion=caja["descripcion"],
                activa=True,
            )

        metodos = {}
        for metodo in METODOS_PAGO:
            metodos[metodo["nombre"]] = MetodoPago.objects.create(
                public_id=calcular_public_id("metodos-pago", metodo["clave"]),
                nombre=metodo["nombre"],
                activo=True,
            )

        esquemas = {}
        for esquema in ESQUEMAS_COMISION:
            esquemas[esquema["nombre"]] = EsquemaComision.objects.create(
                public_id=calcular_public_id("esquemas-comision", esquema["clave"]),
                nombre=esquema["nombre"],
                porcentaje_base=esquema["porcentaje_base"],
                cobra_iva=esquema["cobra_iva"],
                porcentaje_iva=esquema["porcentaje_iva"],
                activo=True,
            )

        canales = {}
        for canal in CANALES_COBRO:
            canales[canal["nombre"]] = CanalCobro.objects.create(
                public_id=calcular_public_id("canales-cobro", canal["clave"]),
                nombre=canal["nombre"],
                metodo_pago=metodos[canal["metodo_pago"]],
                esquema_comision_predeterminado=esquemas[canal["esquema_comision"]],
                activo=True,
            )

        for canal in CANALES_COBRO:
            esquemas[canal["esquema_comision"]].canales_cobro.add(
                canales[canal["nombre"]],
            )

        for origen in ORIGENES_INGRESO:
            OrigenIngreso.objects.create(
                public_id=calcular_public_id("origenes-ingreso", origen["clave"]),
                nombre=origen["nombre"],
                activo=True,
            )

        for concepto in CATALOGO_CONCEPTOS_INGRESO:
            ConceptoIngreso.objects.create(
                public_id=calcular_public_id_concepto(concepto["clave"]),
                nombre=concepto["nombre"],
                descripcion=descripcion_precio_sugerido(concepto),
                permite_material_adicional=concepto["permite_material_adicional"],
                monto_material_sugerido=Decimal("0.00"),
                activo=True,
            )

    def _escribir_resumen(self, prefijo, resumen):
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefijo}: "
                f"{resumen['cajas_fisicas']} cajas físicas, "
                f"{resumen['metodos_pago']} métodos de pago, "
                f"{resumen['esquemas_comision']} esquemas de comisión, "
                f"{resumen['canales_cobro']} canales de cobro, "
                f"{resumen['origenes_ingreso']} orígenes de ingreso, "
                f"{resumen['conceptos_ingreso']} conceptos de ingreso."
            )
        )
