# API de Chremata para Zephyros

## Autenticación de dispositivo

Las rutas bajo `/api/` requieren el header:

```http
X-Archeion-Device-Token: <token-del-dispositivo>
```

No documentar ni commitear tokens reales. Cada Zephyros debe usar su propio token para poder desactivarlo sin afectar otros dispositivos.

## Endpoints

### `GET /api/device/ping/`

Prueba conectividad, disponibilidad de API y validez del token. Útil antes de intentar descargar catálogos o sincronizar.

### `GET /api/v1/catalogos/`

Devuelve snapshot de catálogos activos para captura offline. Zephyros debe conservar `snapshot_id`, `generated_at`, UUIDs públicos y nombres usados durante la captura.

### `GET /api/v1/chremata/schema/`

Devuelve el contrato vigente de Chremata: operaciones soportadas, contratos versionados, campos esperados y reglas de autoridad del servidor.

### `GET /api/v1/chremata/material-pool/`

Devuelve el estado consolidado del material pool. El material pool es económico, no inventario físico.

### `POST /api/v1/chremata/operations/`

Recibe operaciones capturadas por Zephyros. La operación debe incluir, como mínimo:

```json
{
  "operation": "crear_ticket",
  "operation_contract": "chremata.operation.crear_ticket.v1",
  "device_id": "zephyros-cardputer-principal",
  "device_entry_id": "uuid-o-id-estable-del-dispositivo",
  "payload": {}
}
```

## Operaciones soportadas

| Operación | Contrato | Efecto principal |
| --- | --- | --- |
| `crear_ticket` | `chremata.operation.crear_ticket.v1` | Crea un ticket pendiente con sus líneas. No crea ingreso. |
| `cobrar_ticket` | `chremata.operation.cobrar_ticket.v1` | Cobra un ticket pendiente y genera ticket pago e ingreso. |
| `cancelar_ticket` | `chremata.operation.cancelar_ticket.v1` | Cancela un ticket pendiente. No crea ingreso. |
| `abandonar_ticket` | `chremata.operation.abandonar_ticket.v1` | Marca un ticket pendiente como abandonado. No crea ingreso. |
| `crear_gasto_material` | `chremata.operation.crear_gasto_material.v1` | Registra gasto de material y afecta el material pool. |

## Idempotencia

Archeion trata la combinación `device_id + device_entry_id` como llave idempotente.

- Reenviar la misma operación con el mismo payload no debe duplicar tickets, pagos, ingresos ni gastos.
- Si se reenvía la misma llave con payload distinto, Archeion debe responder conflicto.
- Ante timeout o desconexión después de enviar, Zephyros debe reintentar con el mismo `device_entry_id`, no generar uno nuevo.

## Conflicto de payload

Un conflicto ocurre cuando existe una operación previa para el mismo `device_id + device_entry_id`, pero el contenido enviado no coincide con el payload ya registrado. En ese caso, Zephyros debe marcar la operación para revisión y no debe inventar otra operación para ocultar el problema.

## Tickets e ingresos

- Un ticket **pendiente** representa intención de cobro o trabajo capturado, pero no ingreso consolidado.
- Un ticket **cobrado** genera ingreso y ticket pago.
- Un ticket **cancelado** no genera ingreso.
- Un ticket **abandonado** no genera ingreso.
- Solo `cobrar_ticket` debe crear el ingreso oficial asociado al ticket.

## Material pool

El material pool es una medición económica para comparar gastos de material contra cobros explícitos de material. No es inventario físico, no maneja existencias por pieza y no debe usarse para clínicos ni almacén.
