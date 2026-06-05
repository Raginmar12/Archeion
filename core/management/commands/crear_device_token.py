from django.core.management.base import BaseCommand, CommandError

from core.models import DeviceToken


class Command(BaseCommand):
    help = "Crea un token de dispositivo y muestra el secreto una sola vez."

    def add_arguments(self, parser):
        parser.add_argument("nombre", help="Nombre único del dispositivo.")
        parser.add_argument("--notas", default="", help="Notas administrativas.")

    def handle(self, *args, **options):
        nombre = options["nombre"]
        if DeviceToken.objects.filter(nombre=nombre).exists():
            raise CommandError(f'Ya existe un token de dispositivo llamado "{nombre}".')

        device_token, token_completo = DeviceToken.crear(
            nombre=nombre,
            notas=options["notas"],
        )
        self.stdout.write(self.style.SUCCESS(f'Token creado para "{device_token.nombre}".'))
        self.stdout.write("")
        self.stdout.write(token_completo)
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Guarda este token ahora: se muestra una sola vez y no podrá recuperarse."
            )
        )
