# Decisiones de Ledger

## Material como pool económico

Ledger no maneja inventario de material. El material se representa únicamente como un
pool económico que permite comparar los gastos de material registrados contra los
cobros explícitos destinados a recuperarlos.

`ConceptoIngreso.permite_material_adicional` indica si el concepto permite agregar un
cobro de material por separado. Cuando está activo,
`ConceptoIngreso.monto_material_sugerido` representa el monto sugerido para capturar en
`Ingreso.monto_material_cobrado`; el ingreso también puede registrar cero como material
cobrado.

`Ingreso.monto_material_cobrado` representa exclusivamente el monto explícito cobrado
por material adicional. El pool de material solo se recupera con ese campo. Si un
concepto ya incluye material dentro de su precio base, no debe usarse
`monto_material_cobrado`.

Por ahora no se deben editar registros históricos pasados relacionados con ingresos,
comisiones o material, porque pueden alterar fotografías históricas o la secuencia del
pool. Si se necesita corregir historia, se diseñará después un flujo explícito de
ajuste, recálculo o reverso contable.
