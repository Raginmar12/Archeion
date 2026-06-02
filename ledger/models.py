from django.db import models


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
    monto = models.DecimalField(max_digits=10, decimal_places=2)

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

    origen = models.ForeignKey(
        OrigenIngreso,
        on_delete=models.PROTECT,
        related_name="ingresos",
    )

    notas = models.TextField(blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "ingreso"
        verbose_name_plural = "ingresos"

    def __str__(self):
        return f"{self.fecha.date()} - {self.concepto} - ${self.monto}"