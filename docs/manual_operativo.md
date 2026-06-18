# Manual operativo de Archeion y Zephyros

## Antes de consulta

- Encender laptop o Raspberry con Archeion.
- Confirmar que Archeion responde en red local.
- Confirmar que Zephyros tiene batería y SD accesible.
- Revisar que `/zephyros/config.json` tenga `archeion_base_url` correcto.
- Probar conexión con `GET /api/device/ping/` si hubo cambios de red.
- Descargar catálogos si se actualizaron conceptos, métodos de pago, canales o cajas físicas.
- Abrir caja en Zephyros antes de iniciar cobros; esto crea una `CajaSesion` para la operación del día o turno.

## Durante consulta

- Capturar tickets pendientes en Zephyros aunque no haya conexión; crear un ticket pendiente puede hacerse sin caja.
- Evitar reiniciar el dispositivo durante escrituras.
- No editar manualmente `entries_v2.jsonl` durante operación normal.
- Si el ticket todavía no se cobró, mantenerlo como pendiente.
- Cobrar solo cuando realmente se concreta el pago. En Zephyros, cobrar requiere una caja abierta y debe asociar el cobro al `caja_public_id` vigente.
- Registrar gastos de material durante la sesión con la caja abierta cuando correspondan a esa operación.

## Después de consulta

- Conectar Zephyros a la misma red local que Archeion.
- Cerrar caja al final de la consulta o turno, capturando el efectivo contado.
- Ejecutar sincronización.
- Revisar que no queden operaciones `pending` o `error` en `sync_state.json`.
- Revisar en Archeion que los tickets cobrados generaron ingresos.
- Comparar el corte local auxiliar de Zephyros contra el corte oficial de Archeion en `GET /api/v1/chremata/cajas/<caja_public_id>/corte/`.
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


## Flujo recomendado de corte de caja

1. Abrir caja antes de consulta, eligiendo la `CajaFisica` real con llave cuando esté disponible en catálogos.
2. Crear tickets pendientes conforme se necesite; pueden existir sin caja porque todavía no representan ingreso.
3. Cobrar tickets únicamente con caja abierta en Zephyros; el cobro pertenece a la `CajaSesion`, no al ticket pendiente.
4. Registrar gastos de material asociados a la caja si ocurrieron durante la sesión y salieron físicamente de esa caja. Estos gastos aparecen aparte en el corte y reducen el efectivo esperado; los gastos sin `CajaSesion` afectan el material pool global, pero no el corte de una caja específica.
5. Cerrar caja al final con el efectivo contado.
6. Sincronizar todas las operaciones pendientes.
7. Comparar el corte local de Zephyros con el corte oficial de Archeion. Si hay diferencia, Archeion es la fuente de verdad.

## Reporte diario Chremata en Archeion

Archeion expone el reporte diario HTML en la red local en:

```text
/chremata/reportes/dia/
```

La vista requiere usuario y contraseña de Django. Si el usuario no ha iniciado sesión,
Django redirige primero a `/accounts/login/` y después permite consultar el reporte.

Por defecto muestra el día local actual. Para consultar una fecha específica, usar el
parámetro `fecha` en formato `YYYY-MM-DD`:

```text
/chremata/reportes/dia/?fecha=2026-06-18
```

Este reporte diario es un periodo calendario local calculado con la zona horaria
configurada en `ARCHEION_TIME_ZONE`. No es lo mismo que el corte de caja: una
`CajaSesion` puede cruzar medianoche y aparece solo como complemento informativo del
reporte diario cuando intersecta el periodo. El dinero del reporte sale de `Ingreso`,
el desglose por concepto sale de `TicketLinea`, y los gastos de material entran por la
fecha propia de `GastoMaterial`.

También están disponibles reportes HTML de calendario en `/chremata/reportes/semana/`,
`/chremata/reportes/mes/` y `/chremata/reportes/anio/`. Todos requieren login de
Django y reutilizan el mismo servicio de reportes por periodo que el reporte diario.

El corte HTML de una sesión de caja está en `/chremata/cajas/<public_id>/`. Requiere
login, puede consultarse desde teléfono en la red local, usa `calcular_corte_caja()`
y es distinto del endpoint API `/api/v1/chremata/cajas/<caja_public_id>/corte/` que
consume Zephyros.

## Dashboard principal de Chremata

La portada operativa de Chremata está en:

```text
/chremata/
```

Requiere login de Django y está pensada para consultarse desde teléfono o computadora
en la red local. Muestra un resumen de hoy, esta semana y este mes, además de caja
abierta o última caja, material pool actual, últimos cobros y últimos gastos.

El dashboard no reemplaza el Django Admin: el admin sigue siendo el lugar para
mantenimiento detallado de catálogos y revisión de registros. Tampoco reemplaza el
corte de caja, porque el corte pertenece a una `CajaSesion` operativa y puede cruzar
medianoche. El reporte diario detallado sigue disponible en `/chremata/reportes/dia/`.

El dashboard enlaza a los reportes HTML diario, semanal, mensual y anual. Si hay una
caja abierta o una última caja, también enlaza a su corte HTML en `/chremata/cajas/<public_id>/`.
El corte HTML es una vista humana; el endpoint API de corte sigue existiendo para integración.

### Lectura de métricas monetarias

En los reportes y el dashboard de Chremata:

- **Ingresos cobrados** = total cobrado del periodo.
- **Costo de material** = gastos de material registrados por fecha del periodo.
- **Utilidad bruta estimada** = ingresos cobrados - costo de material.
- **Comisiones de cobro** = comisiones de canal o procesador guardadas en los ingresos.
- **Neto operativo básico** = ingresos cobrados - costo de material - comisiones de cobro.
- **Balance material del periodo** = material cobrado - costo de material.

El balance material no es una utilidad: solo compara lo cobrado para recuperar
material contra lo gastado en material dentro del mismo periodo. El neto operativo
básico tampoco es ganancia final real: todavía no descuenta renta, gasolina, equipo,
mantenimiento, impuestos ni otros gastos no registrados.
