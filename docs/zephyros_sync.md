# Contrato de sincronización Zephyros/Chremata

Este documento define el contrato técnico inicial para capturar operaciones de Chremata
desde Zephyros sin conexión y sincronizarlas posteriormente con Archeion. Es un
contrato vigente inicial: Archeion expone catálogos, schema, material pool y recepción
de operaciones Chremata.

## Arquitectura y responsabilidades

Archeion es la fuente principal de datos y la autoridad que consolidará la historia de
Chremata. Zephyros funciona como un dispositivo satélite **offline-first**: debe
poder descargar una fotografía de los catálogos, capturar operaciones localmente sin
conexión y conservarlas hasta que una sincronización futura sea confirmada por
Archeion.

El flujo previsto es:

1. Zephyros descarga un snapshot de catálogos activos desde Archeion.
2. Zephyros conserva el snapshot completo y lo usa para capturar nuevas operaciones.
3. Cada operación se agrega a un registro local append-only con sus referencias UUID y
   una fotografía de los nombres y cálculos mostrados al usuario.
4. Cuando haya conexión, Zephyros enviará operaciones pendientes a un endpoint
   de sincronización.
5. Archeion validará, recalculará comisiones y hará el merge idempotente en la historia
   principal.
6. Zephyros actualizará por separado el estado local de sincronización.

Zephyros no debe editar directamente la historia consolidada. Si posteriormente se
necesitan correcciones, reversos o ajustes, deberán modelarse como operaciones
explícitas y no como mutaciones silenciosas de registros históricos.

## Snapshot de catálogos

### Solicitud

```http
GET /api/v1/catalogos/
X-Archeion-Device-Token: <token-del-dispositivo>
```

La ruta está protegida por el middleware de tokens de dispositivo de Archeion. Cada
dispositivo debe enviar su token mediante el encabezado `X-Archeion-Device-Token`.

### Estructura general de respuesta

```json
{
  "schema_version": 1,
  "snapshot_id": "cat_2026-06-04T23:10:00Z",
  "generated_at": "2026-06-04T23:10:00Z",
  "catalogs": {
    "metodos_pago": [],
    "canales_cobro": [],
    "esquemas_comision": [],
    "conceptos_ingreso": [],
    "origenes_ingreso": []
  }
}
```

- `schema_version` identifica la versión del contrato JSON del snapshot. Zephyros debe
  comprobar que conoce esa versión antes de utilizar el contenido. Un cambio compatible
  puede conservar la versión; un cambio incompatible deberá incrementarla.
- `snapshot_id` identifica la fotografía específica descargada. Debe guardarse junto a
  cada operación capturada para poder determinar qué catálogos vio el dispositivo.
- `generated_at` indica, en formato ISO 8601 timezone-aware, cuándo Archeion generó la
  fotografía.
- `catalogs` contiene únicamente registros activos de los catálogos base de Chremata.
- `public_id` es la identidad pública UUID estable de cada registro de catálogo y debe
  usarse para referencias de sincronización.
- Los campos monetarios y porcentajes decimales viajan como strings, nunca como números
  JSON de punto flotante. Por ejemplo: `"50.00"` y `"4.0600"`.
- Los campos opcionales sin valor viajan como `null`.

El `id` entero de Django puede aparecer en el snapshot como dato auxiliar para Archeion,
pero Zephyros no debe usarlo como identidad durable. Las referencias locales y futuras
solicitudes de sincronización deben usar `public_id`.

## Archivos locales sugeridos

La siguiente estructura separa configuración, catálogos, operaciones inmutables y
estado mutable de sincronización:

Zephyros debe actualizarse para usar estas rutas nuevas; las rutas locales anteriores quedan obsoletas y no deben mezclarse con esta estructura.

| Ruta | Propósito |
| --- | --- |
| `/sd/zephyros/config.json` | Configuración del dispositivo, como `device_id`, URL local de Archeion y credenciales protegidas según las capacidades del dispositivo. |
| `/sd/zephyros/chremata/material_pool_snapshot.json` | Último snapshot completo descargado desde `GET /api/v1/catalogos/`. |
| `/sd/zephyros/chremata/entries_v2.jsonl` | Bitácora append-only de operaciones capturadas localmente, con un objeto JSON por línea. |
| `/sd/zephyros/chremata/sync_state.json` | Estado mutable de sincronización de cada `device_entry_id`. |

`material_pool_snapshot.json` debe reemplazarse de forma segura, por ejemplo escribiendo
primero un archivo temporal completo y después renombrándolo. Una operación ya
capturada debe conservar el `catalog_snapshot_id`, la fecha del snapshot, UUIDs y
nombres congelados que utilizó, aunque posteriormente se descargue un snapshot nuevo.

El token de dispositivo es un secreto. Si se guarda en `config.json`, se deben aplicar
las mejores protecciones disponibles en Zephyros y evitar copiarlo a logs, snapshots u
operaciones.

## Formato recomendado de `entries_v2.jsonl`

`entries_v2.jsonl` contiene una operación JSON completa por línea. Para crear un ingreso,
se recomienda el siguiente contrato inicial:

```json
{"operation":"crear_ingreso","operation_contract":"chremata.operation.crear_ingreso.v1","device_entry_id":"018fca4d-6800-7c20-9c3d-9bbdc43a1abc","device_id":"cardputer-principal","catalog_snapshot_id":"cat_2026-06-04T23:10:00Z","catalog_snapshot_generated_at":"2026-06-04T23:10:00Z","capturado_en_device":"2026-06-05T08:42:17-06:00","device_timezone":"America/Mexico_City","payload":{"concepto_ingreso_public_id":"5be90337-f312-4d8b-ac26-bbefc23160d2","concepto_ingreso_nombre":"Consulta con material","origen_ingreso_public_id":"5e4e2b95-d2c8-4339-9086-55c670882b70","origen_ingreso_nombre":"Consultorio","canal_cobro_public_id":"f076bb64-d59c-42fd-8b95-92c84f455a94","canal_cobro_nombre":"Mercado Pago Tap","metodo_pago_public_id":"655e165d-43da-41d0-a0be-8e23180e6759","metodo_pago_nombre":"Tarjeta","esquema_comision_public_id":"352169aa-f3f1-44b2-a5f4-dfb670e060f4","esquema_comision_nombre":"Mercado Pago 3.5% + IVA","porcentaje_comision_total":"4.0600","monto_procedimiento":"300.00","monto_material_cobrado":"50.00","monto_total":"350.00","comision_calculada_device":"14.21","monto_neto_calculado_device":"335.79","notas":"Capturado sin conexión"}}
```

Aunque el ejemplo aparece en una sola línea porque así se almacena en JSONL, su
estructura lógica es:

- `operation`: tipo de operación; por ejemplo `crear_ingreso`.
- `operation_contract`: contrato versionado de la operación; por ejemplo `chremata.operation.crear_ingreso.v1`.
- `device_entry_id`: UUID generado por Zephyros una sola vez al crear la operación.
- `device_id`: identidad estable del dispositivo que originó la operación.
- `catalog_snapshot_id`: `snapshot_id` del catálogo usado durante la captura.
- `catalog_snapshot_generated_at`: `generated_at` del catálogo usado durante la
  captura.
- `capturado_en_device`: fecha y hora ISO 8601 timezone-aware registrada por el
  dispositivo.
- `device_timezone`: zona horaria IANA configurada durante la captura.
- `payload`: fotografía de referencias, nombres, montos, cálculos y notas de la
  operación.

### Campos de `payload`

| Campo | Descripción |
| --- | --- |
| `concepto_ingreso_public_id` | UUID público del concepto seleccionado. |
| `concepto_ingreso_nombre` | Nombre congelado del concepto mostrado al capturar. |
| `origen_ingreso_public_id` | UUID público del origen seleccionado. |
| `origen_ingreso_nombre` | Nombre congelado del origen mostrado al capturar. |
| `canal_cobro_public_id` | UUID público del canal seleccionado. |
| `canal_cobro_nombre` | Nombre congelado del canal mostrado al capturar. |
| `metodo_pago_public_id` | UUID público del método relacionado con el canal. |
| `metodo_pago_nombre` | Nombre congelado del método mostrado al capturar. |
| `esquema_comision_public_id` | UUID público del esquema usado; puede ser `null` cuando no exista. |
| `esquema_comision_nombre` | Nombre congelado del esquema usado; puede ser `null` cuando no exista. |
| `porcentaje_comision_total` | Porcentaje total calculado en dispositivo, como string decimal. |
| `monto_procedimiento` | Monto base del procedimiento, como string decimal. |
| `monto_material_cobrado` | Monto adicional de material, como string decimal. |
| `monto_total` | Total mostrado en dispositivo, como string decimal. |
| `comision_calculada_device` | Comisión estimada por Zephyros, como string decimal. |
| `monto_neto_calculado_device` | Neto estimado por Zephyros, como string decimal. |
| `notas` | Notas capturadas localmente. |

Los valores calculados por Zephyros son una fotografía útil para auditoría y para
mostrar resultados offline; no sustituyen los cálculos definitivos de Archeion.

## Formato recomendado de `sync_state.json`

El estado de sincronización debe almacenarse separado de `entries_v2.jsonl` para mantener
la bitácora de operaciones append-only. Una estructura inicial sugerida es:

```json
{
  "entries": {
    "018fca4d-6800-7c20-9c3d-9bbdc43a1abc": {
      "status": "pending",
      "attempts": 0,
      "last_attempt_at": null,
      "synced_at": null,
      "archeion_ingreso_id": null,
      "last_error": null
    }
  }
}
```

Cada clave bajo `entries` corresponde a un `device_entry_id`. Los estados previstos
son:

- `pending`: operación local todavía no enviada o lista para reintento.
- `syncing`: intento de envío actualmente en curso.
- `synced`: Archeion confirmó que la operación quedó registrada o ya existía.
- `needs_review`: Archeion recibió la operación, pero requiere revisión humana antes de
  consolidarla.
- `error`: el último intento falló y requiere reintento o intervención.

Campos de seguimiento:

- `attempts`: número acumulado de intentos de sincronización.
- `last_attempt_at`: fecha y hora ISO 8601 timezone-aware del último intento, o `null`.
- `synced_at`: fecha y hora confirmada de sincronización, o `null`.
- `archeion_ingreso_id`: identificador interno devuelto por Archeion para referencia
  auxiliar, o `null`.
- `last_error`: último error útil para diagnóstico, o `null`.

Al escribir `sync_state.json`, Zephyros debe evitar archivos parcialmente escritos;
conviene escribir un archivo temporal completo y renombrarlo de forma atómica cuando
el sistema de archivos lo permita.

## Reglas de confiabilidad e idempotencia

1. `device_entry_id` se genera en Zephyros al crear el registro, antes de cualquier
   intento de sincronización.
2. `device_entry_id` nunca cambia, incluso después de errores, reinicios o reintentos.
3. `entries_v2.jsonl` es append-only: una línea confirmada no debe editarse ni eliminarse.
4. Los registros sincronizados no deben borrarse inmediatamente. Deben conservarse el
   tiempo suficiente para auditoría, recuperación y reintentos seguros.
5. Archeion trata la combinación `device_id + device_entry_id` como llave
   idempotente. Reenviar la misma operación no debe crear ingresos
   duplicados.
6. Archeion recalculará las comisiones al recibir registros. Los cálculos del dispositivo
   se conservarán como fotografía y podrán compararse para detectar diferencias.
7. Todos los montos y porcentajes deben viajar como strings decimales; nunca deben
   convertirse a punto flotante para persistencia o transporte.
8. Los nombres de catálogo se guardan congelados dentro de cada operación para auditoría
   y legibilidad offline, aunque el catálogo sea renombrado posteriormente.
9. `public_id` es la identidad pública estable de los catálogos y debe usarse para el
   merge y la validación de referencias.
10. El `id` entero de Django es interno y auxiliar. No debe ser la identidad durable
    usada por Zephyros.
11. Una respuesta ambigua, desconexión o timeout después de enviar una operación debe
    resolverse reintentando con el mismo `device_id` y `device_entry_id`, nunca creando
    otro identificador para la misma captura.
12. Zephyros solo debe marcar una operación como `synced` después de recibir una
    confirmación explícita de Archeion.

## Ajustes pendientes en Zephyros

- Usar `X-Archeion-Device-Token` en todas las llamadas a `/api/`.
- Usar las rutas `/sd/zephyros/...` documentadas en este archivo.
- Enviar operaciones con `operation` y `operation_contract`.
- Dejar de usar `operation_type`.
- Actualizar cualquier referencia local a ledger, codex o codexhub si queda.

## Alcance pendiente

Este documento todavía no define un flujo para corregir historia mediante ajustes o
reversos contables explícitos.
