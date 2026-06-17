# Decisiones de diseño

## Nombres oficiales

- **Archeion**: servidor Django central y autoridad de datos.
- **Zephyros**: cliente M5Cardputer offline-first.
- **Chremata**: dominio contable/económico dentro de Archeion.
- **MetaboCore**: nombre reservado para futuro sistema clínico, separado de Archeion.

## Chremata no guarda datos clínicos

Chremata registra actividad económica, tickets, cobros, ingresos y material como pool económico. No debe almacenar expedientes, diagnósticos, tratamientos, recetas, laboratorios ni datos clínicos.

## Material pool económico, no inventario

El material pool compara gastos de material contra cobros explícitos de material. No representa existencias físicas, lotes, piezas, caducidades ni almacén clínico.

## Tickets no generan ingreso hasta cobrarse

`crear_ticket` solo crea un ticket pendiente. El ingreso oficial se genera al ejecutar `cobrar_ticket`. Cancelar o abandonar un ticket no genera ingreso.

## No mutar historia sin flujo explícito

Los registros históricos no deben alterarse silenciosamente. Si se necesita corregir historia, debe diseñarse un flujo explícito de reverso, ajuste o recálculo, con operación documentada.

## Idempotencia por dispositivo

Las operaciones sincronizadas se identifican por `device_id + device_entry_id`. Reintentar la misma operación debe ser seguro; cambiar payload con la misma llave es conflicto.

## `operation` + `operation_contract`

El contrato vigente usa `operation` para el nombre de la operación y `operation_contract` para su versión. El campo `operation_type` queda como referencia histórica obsoleta y no debe usarse en nuevas operaciones.

## `seed_chremata_catalogs` solo para base limpia

`seed_chremata_catalogs` carga catálogos iniciales sobre una base limpia. No debe usarse como mecanismo general para modificar catálogos existentes o historia real.

## Seguridad local

Archeion es local-first y privado. No debe exponerse directamente a internet. Los tokens de dispositivo son secretos y no deben aparecer en repositorio, logs ni documentación con valores reales.
