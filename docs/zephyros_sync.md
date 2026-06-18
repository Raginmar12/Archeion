# Contrato vigente de sincronización Zephyros/Chremata

Este documento define el contrato vigente entre Zephyros y Archeion para captura offline-first y sincronización de Chremata.

## Rutas locales en Zephyros

| Ruta | Tipo | Propósito |
| --- | --- | --- |
| `/zephyros/config.json` | JSON normal | Configuración del dispositivo y URL base de Archeion. |
| `/zephyros/chremata/entries_v2.jsonl` | JSONL append-only | Bitácora inmutable de operaciones capturadas localmente. |
| `/zephyros/chremata/sync_state.json` | JSON normal | Estado mutable de sincronización por `device_entry_id`. |
| `/zephyros/chremata/material_pool_snapshot.json` | JSON normal | Último snapshot local útil para vista/resumen de material pool. |
| `/zephyros/chremata/caja_state.json` | JSON normal | Estado local auxiliar de la caja abierta/cerrada en Zephyros. |

## `/zephyros/config.json`

Ejemplo sin secretos reales:

```json
{
  "device_id": "zephyros-cardputer-principal",
  "archeion_base_url": "http://192.168.1.50:8000",
  "archeion_device_token": "REEMPLAZAR_CON_TOKEN_LOCAL",
  "timezone": "America/Mexico_City"
}
```

Reglas:

- `device_id` debe permanecer estable.
- `archeion_base_url` apunta a Archeion en laptop o Raspberry.
- El token es secreto y no debe aparecer en logs ni repositorio.

## `entries_v2.jsonl`

`/zephyros/chremata/entries_v2.jsonl` contiene una operación JSON por línea. Es append-only:

- No editar líneas ya escritas.
- No borrar líneas sincronizadas como mecanismo normal.
- No mezclar JSON pretty-printed; cada operación debe ocupar una sola línea válida.

Campos superiores esperados:

```json
{
  "operation": "crear_ticket",
  "operation_contract": "chremata.operation.crear_ticket.v1",
  "device_id": "zephyros-cardputer-principal",
  "device_entry_id": "018fca4d-6800-7c20-9c3d-9bbdc43a1abc",
  "capturado_en_device": "2026-06-17T10:30:00-06:00",
  "device_timezone": "America/Mexico_City",
  "payload": {}
}
```

## `operation` + `operation_contract`

Contrato vigente:

- Usar `operation` para el tipo de operación.
- Usar `operation_contract` para la versión del contrato.
- No usar `operation_type`; si aparece en archivos viejos, migrarlo o ignorarlo como formato obsoleto.

Operaciones vigentes:

- `crear_ticket` / `chremata.operation.crear_ticket.v1`
- `cobrar_ticket` / `chremata.operation.cobrar_ticket.v1`
- `cancelar_ticket` / `chremata.operation.cancelar_ticket.v1`
- `abandonar_ticket` / `chremata.operation.abandonar_ticket.v1`
- `crear_gasto_material` / `chremata.operation.crear_gasto_material.v1`
- `abrir_caja` / `chremata.operation.abrir_caja.v1`
- `cerrar_caja` / `chremata.operation.cerrar_caja.v1`

## `sync_state.json`

`/zephyros/chremata/sync_state.json` es JSON normal y mutable. Debe registrar estado por `device_entry_id`:

```json
{
  "entries": {
    "018fca4d-6800-7c20-9c3d-9bbdc43a1abc": {
      "status": "pending",
      "attempts": 0,
      "last_attempt_at": null,
      "synced_at": null,
      "last_error": null
    }
  }
}
```

Estados recomendados:

- `pending`: pendiente de envío o reintento.
- `syncing`: intento en curso.
- `synced`: Archeion confirmó recepción idempotente.
- `needs_review`: requiere intervención humana, por ejemplo conflicto de payload.
- `error`: último intento falló.

Si falta el archivo primario, Zephyros debe intentar recuperar desde backup (`sync_state.json.bak` o mecanismo equivalente confirmado en firmware) antes de reconstruir estado desde `entries_v2.jsonl`.

## `material_pool_snapshot.json`

Guarda una fotografía local del material pool para consulta offline. Debe actualizarse de forma segura escribiendo temporal y renombrando cuando el sistema de archivos lo permita.

## Rutas y headers vigentes

Usar:

- Header `X-Archeion-Device-Token`.
- API bajo `/api/...`.
- Rutas locales bajo `/zephyros/...`.

No usar:

- `X-Codex-Device-Token` salvo como referencia histórica obsoleta.
- `/codex` salvo como referencia histórica obsoleta.
- `operation_type` salvo como formato histórico obsoleto.

## Checklist de prueba en Cardputer

1. Confirmar que `/zephyros/config.json` tiene `archeion_base_url` correcto.
2. Confirmar que el token local no está vacío y corresponde a un token activo.
3. Probar `GET /api/device/ping/` desde Zephyros.
4. Descargar catálogos con `GET /api/v1/catalogos/`.
5. Capturar ticket sin conexión o con conexión intermitente.
6. Verificar que se agregó una línea a `entries_v2.jsonl`.
7. Verificar que `sync_state.json` marcó la operación como `pending`.
8. Sincronizar contra Archeion.
9. Confirmar que la operación queda `synced`.
10. Reenviar la misma operación y confirmar que no se duplica.
11. Revisar en Archeion que `cobrar_ticket` genera ingreso y que `crear_ticket` solo deja ticket pendiente.


## Sincronización de caja

- `CajaFisica` es la caja real con llave; Zephyros obtiene `caja_fisica_public_id` desde `cajas_fisicas` de catálogos/schema.
- `CajaSesion` es la sesión operativa de apertura/cierre; `caja_public_id` es su UUID público.
- `abrir_caja` y `cerrar_caja` se sincronizan por `POST /api/v1/chremata/operations/` con campos top-level, igual que el resto de operaciones.
- `cobrar_ticket` y `crear_gasto_material` aceptan `caja_public_id` opcional por compatibilidad temporal; el cliente Zephyros debe enviarlo cuando tenga caja abierta. Si un `GastoMaterial` incluye `caja_public_id`, Archeion lo interpreta como salida física de efectivo de esa `CajaSesion` y lo resta del efectivo esperado del corte. Si no incluye `caja_public_id`, afecta el material pool global, pero no el corte de una caja específica.
- Crear ticket pendiente puede hacerse sin caja. Cobrar ticket en Zephyros requiere caja abierta.
- El corte local de Zephyros es auxiliar para operar offline; el corte oficial se consulta en Archeion con `GET /api/v1/chremata/cajas/<caja_public_id>/corte/`.
- El corte oficial no reemplaza reportes diarios: está delimitado por `CajaSesion` y puede cruzar medianoche.
