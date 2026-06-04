from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import models


PESOS_DECIMALES = Decimal("0.01")
PORCENTAJE_DECIMALES = Decimal("0.0000")
CAMPOS_RECALCULO_COMISION = {
    "monto_bruto",
    "esquema_comision_id",
    "comision_manual",
    "comision",
}
CAMPOS_CALCULADOS_COMISION = {
    "porcentaje_comision_aplicado",
    "comision",
    "monto_neto",
}


class ConceptoIngreso(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "concepto de ingreso"
        verbose_name_plural = "conceptos de ingreso"

    def __str__(self):
        return self.nombre


class MetodoPago(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "método de pago"
        verbose_name_plural = "métodos de pago"

    def __str__(self):
        return self.nombre


class CanalCobro(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    metodo_pago = models.ForeignKey(
        MetodoPago,
        on_delete=models.PROTECT,
        related_name="canales_cobro",
    )
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "canal de cobro"
        verbose_name_plural = "canales de cobro"

    def __str__(self):
        return self.nombre


class EsquemaComision(models.Model):
    canales_cobro = models.ManyToManyField(
        "CanalCobro",
        related_name="esquemas_comision",
        blank=True,
    )
    nombre = models.CharField(max_length=100)
    porcentaje_base = models.DecimalField(max_digits=7, decimal_places=4)
    cobra_iva = models.BooleanField(default=False)
    porcentaje_iva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("16.00"),
    )
    fecha_referencia = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "esquema de comisión"
        verbose_name_plural = "esquemas de comisión"

    def __str__(self):
        return self.nombre

    @property
    def porcentaje_total(self):
        if not self.cobra_iva:
            return self.porcentaje_base

        multiplicador_iva = Decimal("1") + (self.porcentaje_iva / Decimal("100"))
        return (self.porcentaje_base * multiplicador_iva).quantize(PORCENTAJE_DECIMALES)


class OrigenIngreso(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "origen de ingreso"
        verbose_name_plural = "orígenes de ingreso"

    def __str__(self):
        return self.nombre


class Ingreso(models.Model):
    fecha = models.DateTimeField()
    monto_bruto = models.DecimalField(max_digits=10, decimal_places=2)

    concepto = models.ForeignKey(
        ConceptoIngreso,
        on_delete=models.PROTECT,
        related_name="ingresos",
    )

    metodo_pago = models.ForeignKey(
        MetodoPago,
        on_delete=models.PROTECT,
        related_name="ingresos",
    )

    canal_cobro = models.ForeignKey(
        CanalCobro,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ingresos",
    )

    esquema_comision = models.ForeignKey(
        EsquemaComision,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ingresos",
    )

    origen = models.ForeignKey(
        OrigenIngreso,
        on_delete=models.PROTECT,
        related_name="ingresos",
    )

    porcentaje_comision_aplicado = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    comision = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    monto_neto = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    comision_manual = models.BooleanField(default=False)
    notas = models.TextField(blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "ingreso"
        verbose_name_plural = "ingresos"

    def __str__(self):
        return f"{self.fecha.date()} - {self.concepto} - ${self.monto_bruto}"

    def clean(self):
        super().clean()

        if not self.canal_cobro_id or not self.esquema_comision_id:
            return

        esquema_asociado = self.esquema_comision.canales_cobro.filter(
            pk=self.canal_cobro_id,
        ).exists()
        if not esquema_asociado:
            raise ValidationError(
                {
                    "esquema_comision": (
                        "El esquema de comisión seleccionado no está asociado "
                        "al canal de cobro del ingreso."
                    ),
                },
            )

    def calcular_comision(self):
        monto_bruto = (self.monto_bruto or Decimal("0.00")).quantize(PESOS_DECIMALES)

        if self.comision_manual:
            self.comision = (self.comision or Decimal("0.00")).quantize(
                PESOS_DECIMALES,
                rounding=ROUND_HALF_UP,
            )
            self.monto_neto = (monto_bruto - self.comision).quantize(PESOS_DECIMALES)

            if monto_bruto:
                self.porcentaje_comision_aplicado = (
                    (self.comision / monto_bruto) * Decimal("100")
                ).quantize(PORCENTAJE_DECIMALES, rounding=ROUND_HALF_UP)
            return

        if not self.esquema_comision:
            porcentaje = Decimal("0.0000")
        else:
            porcentaje = self.esquema_comision.porcentaje_total

        self.porcentaje_comision_aplicado = porcentaje.quantize(
            PORCENTAJE_DECIMALES,
            rounding=ROUND_HALF_UP,
        )
        self.comision = ((monto_bruto * porcentaje) / Decimal("100")).quantize(
            PESOS_DECIMALES,
            rounding=ROUND_HALF_UP,
        )
        self.monto_neto = (monto_bruto - self.comision).quantize(PESOS_DECIMALES)

    def _debe_recalcular_comision(self, update_fields=None):
        if self._state.adding or not self.pk:
            return True

        if update_fields is not None:
            update_fields = set(update_fields)
            if not update_fields & CAMPOS_RECALCULO_COMISION:
                return False

        try:
            ingreso_previo = Ingreso.objects.filter(pk=self.pk).values(
                *CAMPOS_RECALCULO_COMISION,
            ).get()
        except Ingreso.DoesNotExist:
            return True

        return any(
            ingreso_previo[campo] != getattr(self, campo)
            for campo in CAMPOS_RECALCULO_COMISION
        )

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")

        if self._debe_recalcular_comision(update_fields=update_fields):
            self.calcular_comision()

            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | CAMPOS_CALCULADOS_COMISION

        super().save(*args, **kwargs)
