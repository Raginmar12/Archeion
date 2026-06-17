# Manual operativo de Archeion y Zephyros

## Antes de consulta

- Encender laptop o Raspberry con Archeion.
- Confirmar que Archeion responde en red local.
- Confirmar que Zephyros tiene batería y SD accesible.
- Revisar que `/zephyros/config.json` tenga `archeion_base_url` correcto.
- Probar conexión con `GET /api/device/ping/` si hubo cambios de red.
- Descargar catálogos si se actualizaron conceptos, métodos de pago o canales.

## Durante consulta

- Capturar tickets en Zephyros aunque no haya conexión.
- Evitar reiniciar el dispositivo durante escrituras.
- No editar manualmente `entries_v2.jsonl` durante operación normal.
- Si el ticket todavía no se cobró, mantenerlo como pendiente.
- Cobrar solo cuando realmente se concreta el pago.

## Después de consulta

- Conectar Zephyros a la misma red local que Archeion.
- Ejecutar sincronización.
- Revisar que no queden operaciones `pending` o `error` en `sync_state.json`.
- Revisar en Archeion que los tickets cobrados generaron ingresos.
- Respaldar `db.sqlite3` si fue una sesión importante.

## Probar conexión con laptop

1. Iniciar Archeion:

   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

2. Identificar la IP local de la laptop.
3. Configurar en Zephyros:

   ```json
   {
     "archeion_base_url": "http://IP_DE_LAPTOP:8000"
   }
   ```

4. Probar `/api/device/ping/` con `X-Archeion-Device-Token`.

## Probar conexión con Raspberry

Estado: despliegue final pendiente de formalizar.

Mientras no haya `systemd` final, se puede probar con `runserver` o `gunicorn` en la Raspberry y usar su IP local en `archeion_base_url`.

Pendiente:

- Unidad `systemd` definitiva.
- Usuario de servicio definitivo.
- Política de logs definitiva.
- Ruta final de base de datos y respaldos.

## Si Zephyros no conecta

- Verificar que Archeion está encendido y escuchando en `0.0.0.0:8000` o en el servicio configurado.
- Usar IP local en lugar de `archeion.local`.
- Confirmar que laptop/Raspberry y Zephyros están en la misma red.
- Revisar firewall de Windows si Archeion corre en laptop Windows.
- Confirmar que el token enviado no está vacío, truncado o desactivado.

## Si hay operaciones pendientes

- No borrar `entries_v2.jsonl`.
- Reintentar sincronización con el mismo archivo y el mismo `device_id`.
- Revisar `sync_state.json` para identificar `last_error`.
- Si hay conflicto de payload, marcar para revisión y no crear una operación duplicada artificial.

## Si sync falla

- Probar primero `/api/device/ping/`.
- Probar descarga de catálogos.
- Revisar si el error es 401, 403/503, 409 o 422.
- Mantener operaciones en `pending` o `error` hasta resolver.
- No cambiar `device_entry_id` en reintentos.

## Respaldar `db.sqlite3`

Con Archeion detenido o sin escrituras activas:

```bash
cp db.sqlite3 "db.sqlite3.$(date +%Y%m%d-%H%M%S).bak"
```

Guardar respaldos fuera del repositorio si contienen información real.

## Si el resumen local muestra datos raros

- Confirmar que Zephyros usa el último catálogo descargado.
- Revisar `material_pool_snapshot.json`.
- Verificar que no hay operaciones pendientes de sincronizar.
- Confirmar que las líneas de `entries_v2.jsonl` son JSON válido.
- Comparar contra Archeion; el servidor es la autoridad de datos.
