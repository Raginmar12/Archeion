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

Recibe operaciones capturadas por Zephyros. Importante: aunque `entries_v2.jsonl` usa un envelope local con un objeto `payload`, el endpoint de Archeion **no** recibe un objeto `payload` envolvente. Al sincronizar, Zephyros debe enviar a Archeion los campos específicos de la operación en el nivel raíz del JSON.

En otras palabras:

- En almacenamiento local, Zephyros puede guardar metadatos locales y un `payload` interno dentro de cada línea de `entries_v2.jsonl`.
- En el `POST /api/v1/chremata/operations/`, Zephyros envía el contenido interno de ese `payload` al nivel raíz, junto con `operation`, `operation_contract`, `device_id` y `device_entry_id`.
- Campos como `ticket`, `ticket_public_id`, `fecha_cobro`, `gasto_material`, `fecha_cancelacion` y `fecha_abandono` deben ir top-level, no dentro de `payload`.

## Ejemplos correctos de `POST /api/v1/chremata/operations/`

Los UUIDs siguientes son ejemplos sin datos reales.

### `crear_ticket`

```json
{
  "operation": "crear_ticket",
  "operation_contract": "chremata.operation.crear_ticket.v1",
  "device_id": "zephyros-cardputer-principal",
  "device_entry_id": "018fca4d-6800-7c20-9c3d-9bbdc43a1abc",
  "ticket": {
    "ticket_public_id": "6e3d2c35-4f19-4e17-b01f-2a3a7b31d001",
    "fecha": "2026-06-17T10:00:00-06:00",
    "estado": "pendiente",
    "nombre_referencia": "Referencia operativa",
    "origen_ingreso_public_id": "f35bc673-8dc6-4244-bcc0-558c3e69b001",
    "notas": "Ticket capturado offline",
    "lineas": [
      {
        "concepto_ingreso_public_id": "1d92078f-6517-4912-9dc8-831f1866b001",
        "descripcion": "Consulta",
        "cantidad": "1.00",
        "monto_unitario": "300.00",
        "monto_total": "300.00",
        "monto_material_cobrado": "0.00",
        "orden": 1,
        "notas": ""
      }
    ]
  }
}
```

`crear_ticket` crea un ticket pendiente y no crea ingreso.

### `cobrar_ticket`

```json
{
  "operation": "cobrar_ticket",
  "operation_contract": "chremata.operation.cobrar_ticket.v1",
  "device_id": "zephyros-cardputer-principal",
  "device_entry_id": "018fca4d-6800-7c20-9c3d-9bbdc43a1abd",
  "ticket_public_id": "6e3d2c35-4f19-4e17-b01f-2a3a7b31d001",
  "fecha_cobro": "2026-06-17T10:15:00-06:00",
  "canal_cobro_public_id": "b71aefad-3684-4e81-b457-3c87f1eab001",
  "esquema_comision_public_id": null,
  "concepto_ingreso_resumen_public_id": "1d92078f-6517-4912-9dc8-831f1866b001",
  "notas": "Cobro capturado offline"
}
```

`cobrar_ticket` solo opera sobre tickets pendientes y genera ticket pago e ingreso.

### `crear_gasto_material`

```json
{
  "operation": "crear_gasto_material",
  "operation_contract": "chremata.operation.crear_gasto_material.v1",
  "device_id": "zephyros-cardputer-principal",
  "device_entry_id": "018fca4d-6800-7c20-9c3d-9bbdc43a1abe",
  "gasto_material": {
    "fecha": "2026-06-17T11:00:00-06:00",
    "monto": "120.00",
    "descripcion": "Material de curación",
    "notas": "Compra capturada offline"
  }
}
```

`crear_gasto_material` registra un gasto económico de material y afecta el material pool.

### `cancelar_ticket`

```json
{
  "operation": "cancelar_ticket",
  "operation_contract": "chremata.operation.cancelar_ticket.v1",
  "device_id": "zephyros-cardputer-principal",
  "device_entry_id": "018fca4d-6800-7c20-9c3d-9bbdc43a1abf",
  "ticket_public_id": "6e3d2c35-4f19-4e17-b01f-2a3a7b31d001",
  "fecha_cancelacion": "2026-06-17T11:15:00-06:00",
  "notas": "Cancelación capturada offline"
}
```

`cancelar_ticket` solo opera sobre tickets pendientes y no crea ingreso.

### `abandonar_ticket`

```json
{
  "operation": "abandonar_ticket",
  "operation_contract": "chremata.operation.abandonar_ticket.v1",
  "device_id": "zephyros-cardputer-principal",
  "device_entry_id": "018fca4d-6800-7c20-9c3d-9bbdc43a1ac0",
  "ticket_public_id": "6e3d2c35-4f19-4e17-b01f-2a3a7b31d001",
  "fecha_abandono": "2026-06-17T11:30:00-06:00",
  "notas": "Abandono capturado offline"
}
```

`abandonar_ticket` solo opera sobre tickets pendientes y no crea ingreso.

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

- Reenviar la misma operación con el mismo contenido no debe duplicar tickets, pagos, ingresos ni gastos.
- Si se reenvía la misma llave con contenido distinto, Archeion debe responder conflicto.
- Ante timeout o desconexión después de enviar, Zephyros debe reintentar con el mismo `device_entry_id`, no generar uno nuevo.

## Conflicto de payload

Un conflicto ocurre cuando existe una operación previa para el mismo `device_id + device_entry_id`, pero el contenido enviado no coincide con la operación ya registrada. En ese caso, Zephyros debe marcar la operación para revisión y no debe inventar otra operación para ocultar el problema.

## Tickets e ingresos

- Un ticket **pendiente** representa intención de cobro o trabajo capturado, pero no ingreso consolidado.
- Un ticket **cobrado** genera ingreso y ticket pago.
- Un ticket **cancelado** no genera ingreso.
- Un ticket **abandonado** no genera ingreso.
- Solo `cobrar_ticket` debe crear el ingreso oficial asociado al ticket.

## Material pool

El material pool es una medición económica para comparar gastos de material contra cobros explícitos de material. No es inventario físico, no maneja existencias por pieza y no debe usarse para clínicos ni almacén.
