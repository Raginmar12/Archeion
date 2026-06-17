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
