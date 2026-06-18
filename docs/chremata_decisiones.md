# Decisiones de Chremata

## Montos de un ingreso

`Ingreso.monto_procedimiento` representa el precio base del procedimiento o servicio.
`Ingreso.monto_material_cobrado` representa exclusivamente el monto de material
adicional cobrado por separado. `Ingreso.monto_total` representa el total cobrado y se calcula como la suma del procedimiento y el material adicional.

Las comisiones se calculan sobre `monto_total`, y `monto_neto` representa el total
cobrado menos la comisión aplicada.

## Material como pool económico

Chremata no maneja inventario de material. El material se representa únicamente como un
pool económico que permite comparar los gastos de material registrados contra los
cobros explícitos destinados a recuperarlos.

`ConceptoIngreso.permite_material_adicional` indica si el concepto permite agregar un
cobro de material por separado. Cuando está activo,
`ConceptoIngreso.monto_material_sugerido` representa el monto sugerido para capturar en
`Ingreso.monto_material_cobrado`; el ingreso también puede registrar cero como material
cobrado.

El pool de material solo se recupera con `Ingreso.monto_material_cobrado`. Si un
concepto ya incluye material dentro de su precio base, no debe usarse ese campo.

Por ahora no se deben editar registros históricos pasados relacionados con ingresos,
comisiones o material, porque pueden alterar fotografías históricas o la secuencia del
pool. Si se necesita corregir historia, se diseñará después un flujo explícito de
ajuste, recálculo o reverso contable.

## Precios sugeridos de conceptos

`ConceptoIngreso` todavía no tiene un campo dedicado para precio sugerido. El comando
`seed_chremata_catalogs` solo se ejecuta sobre una base limpia, carga los catálogos
iniciales de Chremata y documenta el precio sugerido en la descripción de cada concepto
para que Zephyros lo use como guía. El monto oficial se captura en Zephyros en la línea
del ticket y Archeion lo consolida al recibir la operación correspondiente.

## Reportes por periodo calendario

Los reportes Chremata por día, semana, mes y año son reportes de calendario en la
zona horaria local configurada por Django. Usan rangos semiabiertos `[inicio, fin)`
para evitar solapamientos entre periodos consecutivos.

El corte de caja sigue siendo un concepto operativo distinto: pertenece a una
`CajaSesion`, puede cruzar medianoche y no define los límites de un reporte diario,
semanal, mensual o anual. En los reportes calendario, las cajas que intersectan el
periodo se muestran solo como complemento informativo.

Para reportes de periodo, `Ingreso` es la fuente oficial de totales monetarios:
importe bruto, procedimiento, material cobrado, material recuperado, material
excedente y comisiones. Las comisiones no se recalculan en el reporte; se leen
las fotografías congeladas guardadas en cada ingreso.

En reportes Chremata, los totales se nombran así:

- Después de comisiones = ingresos cobrados - comisiones de cobro.
- Neto operativo básico = ingresos cobrados - costo de material - comisiones de cobro.
- Balance material del periodo = material cobrado - gastos de material.

El neto operativo básico todavía no descuenta renta, gasolina, equipo,
mantenimiento, impuestos ni otros gastos no registrados como gasto de material del
periodo; por eso no debe interpretarse como ganancia final real.

`TicketPago` se usa para contar tickets cobrados y vincular tickets con líneas e
ingresos, pero no se suma como fuente independiente de dinero. `Ticket.fecha` se
usa solo para actividad operativa de creación, pendientes, cancelados o abandonados;
no se usa para dinero cobrado.

El desglose real por concepto de tickets cobrados sale de `TicketLinea`, filtrada
por la fecha de `TicketPago`. Esto evita colapsar tickets multilínea en el concepto
resumen de `TicketPago` o `Ingreso`. Los ingresos directos sin `TicketPago` se
reportan por separado para no mezclar fuentes de concepto de forma ambigua.

`GastoMaterial` entra al reporte por su propia fecha, tenga o no una caja asociada.
El balance de material del reporte es un balance simple del periodo
(`material cobrado - gastos de material`) y no representa el material pool global.
