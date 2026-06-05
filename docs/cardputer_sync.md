# Contrato inicial de sincronización Cardputer/Codex

Este documento define el contrato técnico inicial para capturar operaciones de Ledger
desde Cardputer/Codex sin conexión y sincronizarlas posteriormente con CodexHub. Es un
diseño preparatorio: por ahora CodexHub solo expone la descarga de catálogos y todavía
no existe un endpoint para subir operaciones.

## Arquitectura y responsabilidades

CodexHub es la fuente principal de datos y la autoridad que consolidará la historia de
Ledger. Cardputer/Codex funciona como un dispositivo satélite **offline-first**: debe
poder descargar una fotografía de los catálogos, capturar operaciones localmente sin
conexión y conservarlas hasta que una sincronización futura sea confirmada por
CodexHub.

El flujo previsto es:

1. Cardputer descarga un snapshot de catálogos activos desde CodexHub.
2. Cardputer conserva el snapshot completo y lo usa para capturar nuevas operaciones.
3. Cada operación se agrega a un registro local append-only con sus referencias UUID y
   una fotografía de los nombres y cálculos mostrados al usuario.
4. Cuando haya conexión, Cardputer enviará operaciones pendientes a un futuro endpoint
   de sincronización.
5. CodexHub validará, recalculará comisiones y hará el merge idempotente en la historia
   principal.
6. Cardputer actualizará por separado el estado local de sincronización.

Cardputer no debe editar directamente la historia consolidada. Si posteriormente se
necesitan correcciones, reversos o ajustes, deberán modelarse como operaciones
explícitas y no como mutaciones silenciosas de registros históricos.

## Snapshot de catálogos

### Solicitud

```http
GET /api/v1/catalogos/
X-Codex-Device-Token: <token-del-dispositivo>
```

La ruta está protegida por el middleware de tokens de dispositivo de CodexHub. Cada
dispositivo debe enviar su token mediante el encabezado `X-Codex-Device-Token`.

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

- `schema_version` identifica la versión del contrato JSON del snapshot. Cardputer debe
  comprobar que conoce esa versión antes de utilizar el contenido. Un cambio compatible
  puede conservar la versión; un cambio incompatible deberá incrementarla.
- `snapshot_id` identifica la fotografía específica descargada. Debe guardarse junto a
  cada operación capturada para poder determinar qué catálogos vio el dispositivo.
- `generated_at` indica, en formato ISO 8601 timezone-aware, cuándo CodexHub generó la
  fotografía.
- `catalogs` contiene únicamente registros activos de los catálogos base de Ledger.
- `public_id` es la identidad pública UUID estable de cada registro de catálogo y debe
  usarse para referencias de sincronización.
- Los campos monetarios y porcentajes decimales viajan como strings, nunca como números
  JSON de punto flotante. Por ejemplo: `"50.00"` y `"4.0600"`.
- Los campos opcionales sin valor viajan como `null`.

El `id` entero de Django puede aparecer en el snapshot como dato auxiliar para CodexHub,
pero Cardputer no debe usarlo como identidad durable. Las referencias locales y futuras
solicitudes de sincronización deben usar `public_id`.

## Archivos locales sugeridos

La siguiente estructura separa configuración, catálogos, operaciones inmutables y
estado mutable de sincronización:

| Ruta | Propósito |
| --- | --- |
| `/sd/codex/config.json` | Configuración del dispositivo, como `device_id`, URL local de CodexHub y credenciales protegidas según las capacidades del dispositivo. |
| `/sd/codex/catalog_snapshot.json` | Último snapshot completo descargado desde `GET /api/v1/catalogos/`. |
| `/sd/codex/entries.jsonl` | Bitácora append-only de operaciones capturadas localmente, con un objeto JSON por línea. |
| `/sd/codex/sync_state.json` | Estado mutable de sincronización de cada `device_entry_id`. |

`catalog_snapshot.json` debe reemplazarse de forma segura, por ejemplo escribiendo
primero un archivo temporal completo y después renombrándolo. Una operación ya
capturada debe conservar el `catalog_snapshot_id`, la fecha del snapshot, UUIDs y
nombres congelados que utilizó, aunque posteriormente se descargue un snapshot nuevo.

El token de dispositivo es un secreto. Si se guarda en `config.json`, se deben aplicar
las mejores protecciones disponibles en Cardputer y evitar copiarlo a logs, snapshots u
operaciones.

## Formato recomendado de `entries.jsonl`

`entries.jsonl` contiene una operación JSON completa por línea. Para crear un ingreso,
se recomienda el siguiente contrato inicial:

```json
{"schema_version":1,"operation_type":"crear_ingreso","device_entry_id":"018fca4d-6800-7c20-9c3d-9bbdc43a1abc","device_id":"cardputer-principal","catalog_snapshot_id":"cat_2026-06-04T23:10:00Z","catalog_snapshot_generated_at":"2026-06-04T23:10:00Z","capturado_en_device":"2026-06-05T08:42:17-06:00","device_timezone":"America/Mexico_City","payload":{"concepto_ingreso_public_id":"5be90337-f312-4d8b-ac26-bbefc23160d2","concepto_ingreso_nombre":"Consulta con material","origen_ingreso_public_id":"5e4e2b95-d2c8-4339-9086-55c670882b70","origen_ingreso_nombre":"Consultorio","canal_cobro_public_id":"f076bb64-d59c-42fd-8b95-92c84f455a94","canal_cobro_nombre":"Mercado Pago Tap","metodo_pago_public_id":"655e165d-43da-41d0-a0be-8e23180e6759","metodo_pago_nombre":"Tarjeta","esquema_comision_public_id":"352169aa-f3f1-44b2-a5f4-dfb670e060f4","esquema_comision_nombre":"Mercado Pago 3.5% + IVA","porcentaje_comision_total":"4.0600","monto_procedimiento":"300.00","monto_material_cobrado":"50.00","monto_total":"350.00","comision_calculada_device":"14.21","monto_neto_calculado_device":"335.79","notas":"Capturado sin conexión"}}
```

Aunque el ejemplo aparece en una sola línea porque así se almacena en JSONL, su
estructura lógica es:

- `schema_version`: versión del contrato de la operación local.
- `operation_type`: tipo de operación; inicialmente se reserva `crear_ingreso`.
- `device_entry_id`: UUID generado por Cardputer una sola vez al crear la operación.
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
| `comision_calculada_device` | Comisión estimada por Cardputer, como string decimal. |
| `monto_neto_calculado_device` | Neto estimado por Cardputer, como string decimal. |
| `notas` | Notas capturadas localmente. |

Los valores calculados por Cardputer son una fotografía útil para auditoría y para
mostrar resultados offline; no sustituyen los cálculos definitivos de CodexHub.

## Formato recomendado de `sync_state.json`

El estado de sincronización debe almacenarse separado de `entries.jsonl` para mantener
la bitácora de operaciones append-only. Una estructura inicial sugerida es:

```json
{
  "entries": {
    "018fca4d-6800-7c20-9c3d-9bbdc43a1abc": {
      "status": "pending",
      "attempts": 0,
      "last_attempt_at": null,
      "synced_at": null,
      "codexhub_ingreso_id": null,
      "last_error": null
    }
  }
}
```

Cada clave bajo `entries` corresponde a un `device_entry_id`. Los estados previstos
son:

- `pending`: operación local todavía no enviada o lista para reintento.
- `syncing`: intento de envío actualmente en curso.
- `synced`: CodexHub confirmó que la operación quedó registrada o ya existía.
- `needs_review`: CodexHub recibió la operación, pero requiere revisión humana antes de
  consolidarla.
- `error`: el último intento falló y requiere reintento o intervención.

Campos de seguimiento:

- `attempts`: número acumulado de intentos de sincronización.
- `last_attempt_at`: fecha y hora ISO 8601 timezone-aware del último intento, o `null`.
- `synced_at`: fecha y hora confirmada de sincronización, o `null`.
- `codexhub_ingreso_id`: identificador interno devuelto por CodexHub para referencia
  auxiliar, o `null`.
- `last_error`: último error útil para diagnóstico, o `null`.

Al escribir `sync_state.json`, Cardputer debe evitar archivos parcialmente escritos;
conviene escribir un archivo temporal completo y renombrarlo de forma atómica cuando
el sistema de archivos lo permita.

## Reglas de confiabilidad e idempotencia

1. `device_entry_id` se genera en Cardputer al crear el registro, antes de cualquier
   intento de sincronización.
2. `device_entry_id` nunca cambia, incluso después de errores, reinicios o reintentos.
3. `entries.jsonl` es append-only: una línea confirmada no debe editarse ni eliminarse.
4. Los registros sincronizados no deben borrarse inmediatamente. Deben conservarse el
   tiempo suficiente para auditoría, recuperación y reintentos seguros.
5. CodexHub deberá tratar la combinación `device_id + device_entry_id` como llave
   idempotente en el futuro. Reenviar la misma operación no debe crear ingresos
   duplicados.
6. CodexHub recalculará las comisiones al recibir registros. Los cálculos del dispositivo
   se conservarán como fotografía y podrán compararse para detectar diferencias.
7. Todos los montos y porcentajes deben viajar como strings decimales; nunca deben
   convertirse a punto flotante para persistencia o transporte.
8. Los nombres de catálogo se guardan congelados dentro de cada operación para auditoría
   y legibilidad offline, aunque el catálogo sea renombrado posteriormente.
9. `public_id` es la identidad pública estable de los catálogos y debe usarse para el
   merge y la validación de referencias.
10. El `id` entero de Django es interno y auxiliar. No debe ser la identidad durable
    usada por Cardputer.
11. Una respuesta ambigua, desconexión o timeout después de enviar una operación debe
    resolverse reintentando con el mismo `device_id` y `device_entry_id`, nunca creando
    otro identificador para la misma captura.
12. Cardputer solo debe marcar una operación como `synced` después de recibir una
    confirmación explícita de CodexHub.

## Alcance pendiente

Este documento no define ni implementa todavía el endpoint de subida, el modelo de
idempotencia en CodexHub, la resolución de conflictos ni un flujo para corregir
historia. Esos contratos deberán diseñarse antes de habilitar la sincronización de
operaciones.
