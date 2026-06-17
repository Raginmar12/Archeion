# Arquitectura de Archeion

## Visión general

Archeion es la autoridad de datos de un sistema local-first para actividad económica personal. Corre como servidor Django central y recibe información desde clientes satélite, principalmente Zephyros en M5Cardputer.

El diseño favorece claridad, auditabilidad y operación local antes que dashboards, APIs públicas o despliegues complejos.

## Componentes

### Archeion

Archeion es el servidor central. Sus responsabilidades actuales son:

- Mantener la base de datos consolidada.
- Exponer catálogos y contratos de sincronización.
- Validar tokens de dispositivo.
- Procesar operaciones idempotentes.
- Consolidar tickets, cobros, ingresos y gastos de material.
- Preservar historia sin mutaciones silenciosas.

### Zephyros

Zephyros es el cliente M5Cardputer offline-first. Sus responsabilidades son:

- Descargar catálogos desde Archeion cuando hay red.
- Capturar tickets y operaciones sin conexión.
- Guardar operaciones en `entries_v2.jsonl` como JSONL append-only.
- Guardar estado mutable de sincronización en `sync_state.json`.
- Reintentar sincronización usando el mismo `device_id` y `device_entry_id`.

Zephyros no es la autoridad final: puede calcular y mostrar resúmenes locales, pero Archeion consolida los datos definitivos.

### Chremata

Chremata es la app/dominio contable de Archeion. Actualmente cubre:

- Catálogos de conceptos, métodos de pago, canales de cobro, esquemas de comisión y orígenes.
- Tickets pendientes, cobrados, cancelados o abandonados.
- Cobros que generan ingresos solo cuando se cobra un ticket.
- Material pool económico.
- Operaciones versionadas con `operation` + `operation_contract`.

### core

`core` concentra seguridad/dispositivos. Actualmente administra tokens de dispositivo usados en el header `X-Archeion-Device-Token`.

## Flujo de datos

1. **Catálogos**: Archeion publica catálogos activos por API.
2. **Captura local**: Zephyros descarga catálogos y permite capturar sin conexión.
3. **Bitácora append-only**: cada captura se agrega a `/zephyros/chremata/entries_v2.jsonl`.
4. **Estado local**: Zephyros actualiza `/zephyros/chremata/sync_state.json` para saber qué está pendiente, sincronizado o con error.
5. **Sync**: al recuperar conexión, Zephyros envía operaciones a `/api/v1/chremata/operations/`.
6. **Operaciones idempotentes**: Archeion usa `device_id + device_entry_id` para evitar duplicados.
7. **Consolidación**: Archeion valida referencias y crea/actualiza tickets, cobros, ingresos y material pool según la operación.

## Estados de ticket

- **Pendiente**: ticket creado pero todavía no cobrado, cancelado ni abandonado.
- **Cobrado**: ticket que generó cobro, ticket pago e ingreso.
- **Cancelado**: ticket descartado explícitamente; no genera ingreso.
- **Abandonado**: ticket no concretado; conserva datos para historia operativa, pero no genera ingreso.

## Qué NO es Archeion

Archeion no es un expediente clínico. No debe contener pacientes, diagnósticos, tratamientos, recetas, laboratorios ni flujos clínicos. El sistema clínico futuro se identifica como MetaboCore, no como Archeion.
