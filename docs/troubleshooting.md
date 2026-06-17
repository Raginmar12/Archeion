# Troubleshooting

## 401 token inválido

Causas probables:

- Falta header `X-Archeion-Device-Token`.
- Token mal copiado o truncado.
- Token desactivado en admin.
- Zephyros está usando un token viejo.

Acciones:

- Crear un token nuevo con `python manage.py crear_device_token "Zephyros"`.
- Actualizar `/zephyros/config.json` sin commitear el secreto.
- Probar `/api/device/ping/`.

## 403/503 configuración de API

Puede indicar configuración incompleta, middleware, entorno no listo o política de acceso. Acciones:

- Ejecutar `python manage.py check`.
- Confirmar que la base fue migrada.
- Confirmar que existe token activo si la API lo requiere.
- Revisar logs de Django.

## Zephyros no resuelve `archeion.local`

Usar IP directa en `archeion_base_url`:

```json
{
  "archeion_base_url": "http://192.168.1.50:8000"
}
```

Confirmar que ambos dispositivos están en la misma red.

## Usar IP de laptop/Raspberry

- En laptop, obtener IP local desde la configuración de red.
- En Raspberry, usar `hostname -I` o la lista de clientes del router.
- Configurar `http://IP:8000` mientras se use `runserver` o `gunicorn` en ese puerto.


## Zephyros no conecta y Archeion responde `400 Bad Request`

Causa probable:

- La IP o hostname usado por `archeion_base_url` no está incluido en `ALLOWED_HOSTS`. Django rechaza la solicitud antes de llegar a la API o al middleware de token.

Solución:

- Agregar a `ALLOWED_HOSTS` el mismo host o IP que usa Zephyros.
- Ejemplo: `ALLOWED_HOSTS=127.0.0.1,localhost,archeion,archeion.local,192.168.1.50`.
- Reiniciar Archeion después de cambiar la variable de entorno.

## Windows firewall

Si Archeion corre en Windows y Zephyros no conecta:

- Permitir Python/Django en red privada.
- Confirmar que el servidor se inició con `0.0.0.0:8000`, no solo `127.0.0.1:8000`.
- Probar desde otro equipo en la misma red.

## Catálogos en cero

Causas probables:

- No se ejecutó `seed_chremata_catalogs` en una base limpia.
- Los catálogos están inactivos.
- Zephyros está leyendo un snapshot viejo.

Acciones:

- En base limpia, ejecutar `python manage.py seed_chremata_catalogs`.
- Revisar Django admin.
- Descargar de nuevo `/api/v1/catalogos/`.

## Operaciones pendientes que no sincronizan

- Revisar `sync_state.json` y `last_error`.
- Probar conectividad con `/api/device/ping/`.
- Confirmar token válido.
- Confirmar que `entries_v2.jsonl` contiene JSON válido por línea.
- No regenerar `device_entry_id` para reintentos.

## Payload conflict

Significa que Archeion ya recibió una operación con el mismo `device_id + device_entry_id`, pero el payload nuevo es distinto.

Acciones:

- Marcar la operación como `needs_review`.
- No crear otra operación para duplicar el efecto.
- Comparar la línea local de `entries_v2.jsonl` con lo registrado en Archeion.

## `sync_state.json` perdido/restaurado desde `.bak`

Si falta el archivo principal:

1. Intentar restaurar `sync_state.json.bak` o backup equivalente.
2. Si no hay backup, reconstruir estado desde `entries_v2.jsonl` marcando como pendientes las operaciones no confirmadas.
3. Reintentar sincronización; la idempotencia de Archeion evita duplicados si se conserva `device_id + device_entry_id`.

## `entries_v2.jsonl` corrupto o con líneas inválidas

- No borrar el archivo completo.
- Identificar líneas inválidas.
- Conservar copia forense antes de editar.
- Recuperar operaciones válidas línea por línea.
- Marcar operaciones dudosas para revisión manual.
- Evitar pretty-print; JSONL requiere un objeto JSON completo por línea.


## `caja_abierta_exists` al abrir caja

Archeion encontró una `CajaSesion` abierta para el mismo `device_id`. Acciones:

- No generar otra caja artificial.
- Revisar si Zephyros ya había abierto caja y perdió estado local.
- Consultar o recuperar el `caja_public_id` de la caja abierta antes de seguir cobrando.
- Si la sesión realmente terminó, cerrarla con `cerrar_caja` y luego abrir una nueva.

## Zephyros perdió `caja_state.json` pero Archeion tiene caja abierta

`caja_state.json` es auxiliar local; la autoridad es Archeion. Acciones:

- No borrar ni reescribir `entries_v2.jsonl`.
- Buscar en `entries_v2.jsonl` la operación `abrir_caja` sincronizada o pendiente y recuperar su `caja_public_id`.
- Si no se puede reconstruir localmente, revisar Archeion/admin para identificar la `CajaSesion` abierta del `device_id`.
- Rehidratar el estado local con ese `caja_public_id` y continuar; si hay duda, cerrar caja y documentar la incidencia.

## Se reinició DB de Archeion pero Zephyros conserva `entries_v2.jsonl`/`caja_state.json`

Esto deja a Zephyros apuntando a UUIDs que pueden no existir en la base limpia de Archeion. Acciones:

- Descargar catálogos otra vez después de `migrate` y `seed_chremata_catalogs`.
- No sincronizar automáticamente operaciones antiguas contra una base limpia sin revisión.
- Si `caja_state.json` conserva una caja abierta que Archeion ya no conoce, cerrar o archivar el estado local y abrir una nueva caja sobre la base actual.
- Esperar errores 422/404 por `caja_public_id`, `caja_fisica_public_id` o catálogos inexistentes si se intenta reenviar historia vieja.

## 422 al sincronizar `abrir_caja` o `cerrar_caja`

Causas frecuentes:

- `abrir_caja`: ya existe caja abierta para el dispositivo (`caja_abierta_exists`).
- `abrir_caja`: `caja_fisica_public_id` no existe o la caja física está inactiva.
- `abrir_caja`: `saldo_inicial_efectivo` negativo o inválido.
- `cerrar_caja`: la caja no está abierta.
- `cerrar_caja`: `cerrada_en` es anterior a `abierta_en`.
- `cerrar_caja`: `efectivo_contado_cierre` negativo o inválido.

Acciones: corregir el estado operativo real, mantener el mismo `device_entry_id` para reintentos idempotentes cuando el payload sea el mismo, y marcar para revisión si cambiar el payload altera la operación original.

## Diferencia entre corte local y corte oficial

El corte local de Zephyros es auxiliar. El corte oficial vive en Archeion y se consulta con `GET /api/v1/chremata/cajas/<caja_public_id>/corte/`. Revisar:

- Que todas las operaciones estén `synced`.
- Que los cobros tengan el `caja_public_id` correcto.
- Que los totales por concepto en Archeion salen de `TicketLinea`, no del concepto resumen del pago.
- Que `efectivo_esperado = saldo_inicial_efectivo + total_efectivo`.
- Que gastos de material se reportan aparte y no restan efectivo esperado.

## Cobros sin caja por compatibilidad temporal

Archeion todavía acepta `cobrar_ticket` y `crear_gasto_material` sin `caja_public_id` por compatibilidad temporal. En operación oficial de Zephyros, cobrar requiere caja abierta. Si aparecen cobros sin caja:

- Revisar versión/configuración de Zephyros.
- No asumir que aparecerán en un corte de caja específico.
- Corregir el flujo operativo para abrir caja antes de cobrar.
