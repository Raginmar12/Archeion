from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum


PESOS_DECIMALES = Decimal("0.01")
PORCENTAJE_DECIMALES = Decimal("0.0000")
CAMPOS_RECALCULO_COMISION = {
    "monto_bruto",
    "canal_cobro_id",
    "esquema_comision_id",
    "comision_manual",
    "comision",
}
CAMPOS_RECALCULO_COMISION_UPDATE_FIELDS = CAMPOS_RECALCULO_COMISION | {
    "canal_cobro",
    "esquema_comision",
}
CAMPOS_CALCULADOS_COMISION = {
    "porcentaje_comision_aplicado",
    "comision",
    "monto_neto",
}
CAMPOS_RECALCULO_MATERIAL = {"monto_material_cobrado"}
CAMPOS_CALCULADOS_MATERIAL = {
    "material_recuperado",
    "material_excedente",
    "pool_material_antes",
    "pool_material_despues",
}


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
    permite_material_adicional = models.BooleanField(
        default=False,
        verbose_name="permite material adicional",
    )
    monto_material_sugerido = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="monto material sugerido",
    )
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
    esquema_comision_predeterminado = models.ForeignKey(
        "EsquemaComision",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="canales_predeterminados",
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

    def clean(self):
        super().clean()

        if not self.pk or not self.esquema_comision_predeterminado_id:
            return

        esquema_asociado = (
            self.esquema_comision_predeterminado.canales_cobro.filter(
                pk=self.pk,
            ).exists()
        )
        if not esquema_asociado:
            raise ValidationError(
                {
                    "esquema_comision_predeterminado": (
                        "El esquema de comisión predeterminado debe estar "
                        "asociado a este canal de cobro."
                    ),
                },
            )


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


class GastoMaterial(models.Model):
    fecha = models.DateTimeField()
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    descripcion = models.CharField(max_length=200, blank=True)
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "gasto de material"
        verbose_name_plural = "gastos de material"

    def __str__(self):
        return f"{self.fecha.date()} - ${self.monto}"


class Ingreso(models.Model):
    fecha = models.DateTimeField()
    monto_bruto = models.DecimalField(max_digits=10, decimal_places=2)

    concepto = models.ForeignKey(
        ConceptoIngreso,
        on_delete=models.PROTECT,
        related_name="ingresos",
    )

    canal_cobro = models.ForeignKey(
        CanalCobro,
        on_delete=models.PROTECT,
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
    monto_material_cobrado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    material_recuperado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    material_excedente = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    pool_material_antes = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    pool_material_despues = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    notas = models.TextField(blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "ingreso"
        verbose_name_plural = "ingresos"

    def __str__(self):
        return f"{self.fecha.date()} - {self.concepto} - ${self.monto_bruto}"

    @property
    def metodo_pago(self):
        if self.canal_cobro_id:
            return self.canal_cobro.metodo_pago
        return None

    def asignar_esquema_predeterminado(self):
        if self.esquema_comision_id or not self.canal_cobro_id:
            return False

        esquema_predeterminado = self.canal_cobro.esquema_comision_predeterminado
        if not esquema_predeterminado:
            return False

        self.esquema_comision = esquema_predeterminado
        return True

    @classmethod
    def calcular_pool_material_actual(cls, excluir_ingreso_id=None):
        total_gastos = GastoMaterial.objects.aggregate(
            total=Sum("monto"),
        )["total"] or Decimal("0.00")

        ingresos = cls.objects.all()
        if excluir_ingreso_id:
            ingresos = ingresos.exclude(pk=excluir_ingreso_id)

        total_recuperado = ingresos.aggregate(
            total=Sum("material_recuperado"),
        )["total"] or Decimal("0.00")

        pool = total_gastos - total_recuperado
        if pool < Decimal("0.00"):
            return Decimal("0.00")
        return pool.quantize(PESOS_DECIMALES)

    def validar_material(self):
        monto_material_cobrado = (
            self.monto_material_cobrado or Decimal("0.00")
        ).quantize(PESOS_DECIMALES)

        if (
            monto_material_cobrado > Decimal("0.00")
            and not self.concepto.permite_material_adicional
        ):
            raise ValidationError(
                {
                    "monto_material_cobrado": (
                        "Este concepto no permite cobrar material adicional."
                    ),
                },
            )

    def calcular_material(self):
        monto_material_cobrado = (
            self.monto_material_cobrado or Decimal("0.00")
        ).quantize(PESOS_DECIMALES, rounding=ROUND_HALF_UP)
        self.monto_material_cobrado = monto_material_cobrado

        if monto_material_cobrado <= Decimal("0.00"):
            self.material_recuperado = Decimal("0.00")
            self.material_excedente = Decimal("0.00")
            self.pool_material_antes = Decimal("0.00")
            self.pool_material_despues = Decimal("0.00")
            return

        pool_material_antes = self.calcular_pool_material_actual(
            excluir_ingreso_id=self.pk,
        )
        material_recuperado = min(monto_material_cobrado, pool_material_antes)
        material_excedente = monto_material_cobrado - material_recuperado

        self.pool_material_antes = pool_material_antes.quantize(PESOS_DECIMALES)
        self.material_recuperado = material_recuperado.quantize(PESOS_DECIMALES)
        self.material_excedente = material_excedente.quantize(PESOS_DECIMALES)
        self.pool_material_despues = (
            pool_material_antes - material_recuperado
        ).quantize(PESOS_DECIMALES)

    def validar_canal_y_esquema_comision(self):
        errores = {}

        if not self.canal_cobro_id:
            errores["canal_cobro"] = "Todo ingreso debe tener un canal de cobro."

        if self.canal_cobro_id:
            self.asignar_esquema_predeterminado()

        if not self.esquema_comision_id:
            errores["esquema_comision"] = (
                "Todo ingreso debe tener un esquema de comisión. "
                "Selecciona uno o configura un esquema predeterminado para el canal."
            )

        if self.canal_cobro_id and self.esquema_comision_id:
            esquema_asociado = self.esquema_comision.canales_cobro.filter(
                pk=self.canal_cobro_id,
            ).exists()
            if not esquema_asociado:
                errores["esquema_comision"] = (
                    "El esquema de comisión seleccionado no está asociado "
                    "al canal de cobro del ingreso."
                )

        if errores:
            raise ValidationError(errores)

    def clean(self):
        super().clean()
        self.validar_canal_y_esquema_comision()
        self.validar_material()

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
            if not update_fields & CAMPOS_RECALCULO_COMISION_UPDATE_FIELDS:
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

    def _debe_recalcular_material(self, update_fields=None):
        if self._state.adding or not self.pk:
            return True

        if update_fields is not None:
            update_fields = set(update_fields)
            if not update_fields & CAMPOS_RECALCULO_MATERIAL:
                return False

        try:
            ingreso_previo = Ingreso.objects.filter(pk=self.pk).values(
                *CAMPOS_RECALCULO_MATERIAL,
            ).get()
        except Ingreso.DoesNotExist:
            return True

        return any(
            ingreso_previo[campo] != getattr(self, campo)
            for campo in CAMPOS_RECALCULO_MATERIAL
        )

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        esquema_asignado = self.asignar_esquema_predeterminado()

        self.validar_canal_y_esquema_comision()
        self.validar_material()

        debe_recalcular_comision = self._debe_recalcular_comision(
            update_fields=update_fields,
        )
        debe_recalcular_material = self._debe_recalcular_material(
            update_fields=update_fields,
        )

        campos_extra_update = set()
        if debe_recalcular_comision or esquema_asignado:
            self.calcular_comision()
            campos_extra_update |= CAMPOS_CALCULADOS_COMISION | {"esquema_comision"}

        if debe_recalcular_material:
            self.calcular_material()
            campos_extra_update |= CAMPOS_CALCULADOS_MATERIAL

        if update_fields is not None and campos_extra_update:
            kwargs["update_fields"] = set(update_fields) | campos_extra_update

        super().save(*args, **kwargs)
