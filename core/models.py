import hashlib
import secrets

from django.db import models


TOKEN_PREFIX = "archeion_"
PREFIJO_VISIBLE_LONGITUD = 24


class DeviceToken(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    token_hash = models.CharField(max_length=128, unique=True, editable=False)
    prefijo = models.CharField(max_length=24, blank=True, editable=False)
    activo = models.BooleanField(default=True)
    ultimo_uso_en = models.DateTimeField(null=True, blank=True)
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "token de dispositivo"
        verbose_name_plural = "tokens de dispositivo"

    def __str__(self):
        return self.nombre

    @staticmethod
    def generar_token_completo():
        return f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"

    @staticmethod
    def calcular_hash(token_completo):
        return hashlib.sha256(token_completo.encode("utf-8")).hexdigest()

    @classmethod
    def crear(cls, nombre, notas=""):
        token_completo = cls.generar_token_completo()
        token = cls.objects.create(
            nombre=nombre,
            notas=notas,
            token_hash=cls.calcular_hash(token_completo),
            prefijo=token_completo[:PREFIJO_VISIBLE_LONGITUD],
        )
        return token, token_completo
