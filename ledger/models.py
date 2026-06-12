import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

PESOS_DECIMALES = Decimal("0.01")
PORCENTAJE_DECIMALES = Decimal("0.0000")
CAMPOS_RECALCULO_COMISION = {
    "monto_procedimiento",
    "monto_material_cobrado",
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
    "monto_total",
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


class ConceptoIngreso(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    nombre = models.CharField(max_length=50, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "método de pago"
        verbose_name_plural = "métodos de pago"

    def __str__(self):
        return self.nombre


class CanalCobro(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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

        esquema_asociado = self.esquema_comision_predeterminado.canales_cobro.filter(
            pk=self.pk,
        ).exists()
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
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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


class Ticket(models.Model):
    ESTADO_PENDIENTE = "pendiente"
    ESTADO_COBRADO = "cobrado"
    ESTADO_CANCELADO = "cancelado"
    ESTADO_ABANDONADO = "abandonado"

    ESTADOS = (
        (ESTADO_PENDIENTE, "pendiente"),
        (ESTADO_COBRADO, "cobrado"),
        (ESTADO_CANCELADO, "cancelado"),
        (ESTADO_ABANDONADO, "abandonado"),
    )

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    fecha = models.DateTimeField()
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default=ESTADO_PENDIENTE,
    )
    nombre_referencia = models.CharField(max_length=150, blank=True)
    origen = models.ForeignKey(
        OrigenIngreso,
        on_delete=models.PROTECT,
        related_name="tickets",
    )
    notas = models.TextField(blank=True)
    monto_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    monto_material_cobrado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "ticket"
        verbose_name_plural = "tickets"

    def __str__(self):
        referencia = f" - {self.nombre_referencia}" if self.nombre_referencia else ""
        return f"{self.fecha.date()}{referencia} - {self.estado} - ${self.monto_total}"

    @property
    def monto_total_cobrado(self):
        return (
            (self.monto_total or Decimal("0.00"))
            + (self.monto_material_cobrado or Decimal("0.00"))
        ).quantize(PESOS_DECIMALES)

    def recalcular_totales(self, guardar=True):
        if not self.pk:
            self.monto_total = Decimal("0.00")
            self.monto_material_cobrado = Decimal("0.00")
            return

        totales = self.lineas.aggregate(
            monto_total=Sum("monto_total"),
            monto_material_cobrado=Sum("monto_material_cobrado"),
        )
        self.monto_total = (totales["monto_total"] or Decimal("0.00")).quantize(
            PESOS_DECIMALES
        )
        self.monto_material_cobrado = (
            totales["monto_material_cobrado"] or Decimal("0.00")
        ).quantize(PESOS_DECIMALES)

        if guardar:
            self.save(update_fields=["monto_total", "monto_material_cobrado"])


class TicketLinea(models.Model):
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="lineas",
    )
    concepto = models.ForeignKey(
        ConceptoIngreso,
        on_delete=models.PROTECT,
        related_name="ticket_lineas",
    )
    descripcion = models.CharField(max_length=200, blank=True)
    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
    )
    monto_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    monto_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    monto_material_cobrado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    orden = models.PositiveIntegerField(default=0)
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ticket", "orden", "id"]
        verbose_name = "línea de ticket"
        verbose_name_plural = "líneas de ticket"

    def __str__(self):
        return f"{self.ticket_id} - {self.concepto} - ${self.monto_total}"

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

    def calcular_total(self):
        cantidad = (self.cantidad or Decimal("0.00")).quantize(
            PESOS_DECIMALES,
            rounding=ROUND_HALF_UP,
        )
        monto_unitario = (self.monto_unitario or Decimal("0.00")).quantize(
            PESOS_DECIMALES,
            rounding=ROUND_HALF_UP,
        )
        monto_material_cobrado = (
            self.monto_material_cobrado or Decimal("0.00")
        ).quantize(PESOS_DECIMALES, rounding=ROUND_HALF_UP)

        self.cantidad = cantidad
        self.monto_unitario = monto_unitario
        self.monto_material_cobrado = monto_material_cobrado
        self.monto_total = (cantidad * monto_unitario).quantize(
            PESOS_DECIMALES,
            rounding=ROUND_HALF_UP,
        )

    def clean(self):
        super().clean()
        self.validar_material()

    def save(self, *args, **kwargs):
        self.validar_material()
        self.calcular_total()
        super().save(*args, **kwargs)
        self.ticket.recalcular_totales()

    def delete(self, *args, **kwargs):
        ticket = self.ticket
        resultado = super().delete(*args, **kwargs)
        ticket.recalcular_totales()
        return resultado


class Ingreso(models.Model):
    fecha = models.DateTimeField()
    monto_procedimiento = models.DecimalField(max_digits=10, decimal_places=2)
    monto_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

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
        return f"{self.fecha.date()} - {self.concepto} - ${self.monto_total}"

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
        )[
            "total"
        ] or Decimal("0.00")

        ingresos = cls.objects.all()
        if excluir_ingreso_id:
            ingresos = ingresos.exclude(pk=excluir_ingreso_id)

        total_recuperado = ingresos.aggregate(
            total=Sum("material_recuperado"),
        )[
            "total"
        ] or Decimal("0.00")

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
        monto_procedimiento = (self.monto_procedimiento or Decimal("0.00")).quantize(
            PESOS_DECIMALES, rounding=ROUND_HALF_UP
        )
        monto_material_cobrado = (
            self.monto_material_cobrado or Decimal("0.00")
        ).quantize(PESOS_DECIMALES, rounding=ROUND_HALF_UP)

        self.monto_procedimiento = monto_procedimiento
        self.monto_material_cobrado = monto_material_cobrado
        self.monto_total = (monto_procedimiento + monto_material_cobrado).quantize(
            PESOS_DECIMALES,
        )

        if self.comision_manual:
            self.comision = (self.comision or Decimal("0.00")).quantize(
                PESOS_DECIMALES,
                rounding=ROUND_HALF_UP,
            )
            self.monto_neto = (self.monto_total - self.comision).quantize(
                PESOS_DECIMALES,
            )
            self.porcentaje_comision_aplicado = Decimal("0.0000")
            if self.monto_total:
                self.porcentaje_comision_aplicado = (
                    (self.comision / self.monto_total) * Decimal("100")
                ).quantize(PORCENTAJE_DECIMALES, rounding=ROUND_HALF_UP)
            return

        porcentaje = self.esquema_comision.porcentaje_total

        self.porcentaje_comision_aplicado = porcentaje.quantize(
            PORCENTAJE_DECIMALES,
            rounding=ROUND_HALF_UP,
        )
        self.comision = ((self.monto_total * porcentaje) / Decimal("100")).quantize(
            PESOS_DECIMALES,
            rounding=ROUND_HALF_UP,
        )
        self.monto_neto = (self.monto_total - self.comision).quantize(PESOS_DECIMALES)

    def _debe_recalcular_comision(self, update_fields=None):
        if self._state.adding or not self.pk:
            return True

        if update_fields is not None:
            update_fields = set(update_fields)
            if not update_fields & CAMPOS_RECALCULO_COMISION_UPDATE_FIELDS:
                return False

        try:
            ingreso_previo = (
                Ingreso.objects.filter(pk=self.pk)
                .values(
                    *CAMPOS_RECALCULO_COMISION,
                )
                .get()
            )
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
            ingreso_previo = (
                Ingreso.objects.filter(pk=self.pk)
                .values(
                    *CAMPOS_RECALCULO_MATERIAL,
                )
                .get()
            )
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
        if debe_recalcular_material:
            self.calcular_material()
            campos_extra_update |= CAMPOS_CALCULADOS_MATERIAL

        if debe_recalcular_comision or esquema_asignado:
            self.calcular_comision()
            campos_extra_update |= CAMPOS_CALCULADOS_COMISION | {"esquema_comision"}

        if update_fields is not None and campos_extra_update:
            kwargs["update_fields"] = set(update_fields) | campos_extra_update

        super().save(*args, **kwargs)


class TicketPago(models.Model):
    ticket = models.OneToOneField(
        Ticket,
        on_delete=models.PROTECT,
        related_name="pago",
    )
    ingreso = models.OneToOneField(
        Ingreso,
        on_delete=models.PROTECT,
        related_name="ticket_pago",
    )
    fecha = models.DateTimeField()
    canal_cobro = models.ForeignKey(
        CanalCobro,
        on_delete=models.PROTECT,
        related_name="ticket_pagos",
    )
    esquema_comision = models.ForeignKey(
        EsquemaComision,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ticket_pagos",
    )
    concepto_ingreso = models.ForeignKey(
        ConceptoIngreso,
        on_delete=models.PROTECT,
        related_name="ticket_pagos",
    )
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "pago de ticket"
        verbose_name_plural = "pagos de ticket"

    def __str__(self):
        return (
            f"{self.fecha.date()} - ticket {self.ticket_id} - ingreso {self.ingreso_id}"
        )


class OperacionDispositivoChremata(models.Model):
    STATUS_RECEIVED = "received"
    STATUS_PROCESSED = "processed"
    STATUS_FAILED = "failed"
    STATUS_CONFLICT = "conflict"

    STATUS_CHOICES = (
        (STATUS_RECEIVED, "received"),
        (STATUS_PROCESSED, "processed"),
        (STATUS_FAILED, "failed"),
        (STATUS_CONFLICT, "conflict"),
    )

    device_id = models.CharField(max_length=100)
    device_entry_id = models.CharField(max_length=100)
    operation = models.CharField(max_length=50)
    operation_contract = models.CharField(max_length=150)
    payload = models.JSONField()
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_RECEIVED,
    )
    response = models.JSONField(null=True, blank=True)
    error = models.JSONField(null=True, blank=True)
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operaciones_dispositivo",
    )
    ingreso = models.ForeignKey(
        Ingreso,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operaciones_dispositivo",
    )
    ticket_pago = models.ForeignKey(
        TicketPago,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operaciones_dispositivo",
    )
    gasto_material = models.ForeignKey(
        GastoMaterial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operaciones_dispositivo",
    )
    recibido_en = models.DateTimeField(auto_now_add=True)
    procesado_en = models.DateTimeField(null=True, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-recibido_en", "-id"]
        verbose_name = "operación de dispositivo Chremata"
        verbose_name_plural = "operaciones de dispositivo Chremata"
        constraints = [
            models.UniqueConstraint(
                fields=["device_id", "device_entry_id"],
                name="uniq_chremata_operation_device_entry",
            ),
        ]

    def __str__(self):
        return f"{self.device_id} - {self.device_entry_id} - {self.operation}"
