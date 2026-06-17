# Archeion

Archeion es el servidor Django central de un ecosistema privado y local-first para registrar actividad económica personal. Su dominio activo es **Chremata**, enfocado en tickets, cobros, ingresos, métodos de pago, canales de cobro, comisiones y material como pool económico.

Archeion **no** es un expediente clínico, no almacena datos de pacientes y no debe crecer hacia diagnósticos, tratamientos, recetas, laboratorios ni flujos clínicos salvo una solicitud explícita futura.

## Relación Archeion / Zephyros / Chremata

- **Archeion**: autoridad de datos y servidor Django central. Consolida catálogos, tickets, ingresos, operaciones idempotentes y material pool.
- **Zephyros**: cliente M5Cardputer offline-first. Captura operaciones localmente, guarda bitácoras JSONL append-only y sincroniza cuando Archeion está disponible en la red local.
- **Chremata**: app y dominio contable dentro de Archeion. Modela tickets, cobros, ingresos, gastos de material, catálogos y reglas de comisión.
- **core**: app de seguridad y dispositivos. Administra tokens de dispositivo usados por la API local.

## Estado actual del proyecto

Confirmado actualmente:

- Archeion funciona como servidor Django central en red local.
- Zephyros ya pudo actualizar catálogos desde Archeion corriendo en laptop.
- Zephyros ya pudo sincronizar tickets correctamente con Archeion.
- La API usa el header `X-Archeion-Device-Token`.
- Zephyros usa `archeion_base_url` en `/zephyros/config.json`.
- Zephyros usa rutas locales bajo `/zephyros/...` y `/zephyros/chremata/...`.
- Chremata usa `operation` + `operation_contract` para operaciones sincronizadas.
- El flujo oficial de caja usa `CajaFisica` como caja real con llave y `CajaSesion` como apertura/cierre operativa.
- `caja_public_id` identifica una `CajaSesion`; `caja_fisica_public_id` identifica una `CajaFisica`.
- El corte de caja oficial vive en Archeion y se consulta por sesión; no reemplaza el reporte diario y puede cruzar medianoche.
- `entries_v2.jsonl` es JSONL append-only.
- `sync_state.json` es JSON normal y mutable.
- `seed_chremata_catalogs` carga catálogos iniciales solo sobre una base limpia.

Pendiente o no formalizado:

- Despliegue final en Raspberry con `systemd`.
- Política futura de reversos, ajustes o recálculos históricos.
- Exposición remota segura; Archeion no debe exponerse directamente a internet.

## Stack técnico

- Python
- Django
- SQLite para desarrollo/local-first
- Django admin
- API HTTP JSON protegida con tokens de dispositivo
- Zephyros/M5Cardputer como cliente offline-first

## Instalación local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

En Windows PowerShell, la activación del entorno virtual puede variar:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Flujo limpio de base de datos

Usar este flujo cuando se quiera iniciar desde cero y cargar catálogos iniciales:

```bash
rm -f db.sqlite3
python manage.py migrate
python manage.py seed_chremata_catalogs
python manage.py createsuperuser
python manage.py crear_device_token "Zephyros"
python manage.py runserver 0.0.0.0:8000
```

Notas importantes:

- No incluir tokens reales en documentación, commits, capturas ni logs.
- `seed_chremata_catalogs` está pensado para base limpia; no usarlo como migración de datos históricos.
- El token mostrado por `crear_device_token` debe copiarse en el dispositivo una sola vez y guardarse fuera del repositorio.

## Variables y configuración importantes

- `X-Archeion-Device-Token`: header obligatorio para rutas protegidas bajo `/api/`.
- `ARCHEION_DEVICE_TOKEN`: fallback temporal/de emergencia si no hay tokens activos en base de datos. Cuando existe al menos un token activo en base, la API exige un token activo de base de datos.
- `archeion_base_url`: URL base usada por Zephyros para llegar a Archeion desde la red local.
- `ALLOWED_HOSTS`: lista separada por comas de hosts/IPs aceptados por Django. Si Zephyros usa una IP LAN en `archeion_base_url`, esa IP también debe estar incluida aquí.
- `db.sqlite3`: base SQLite local; debe respaldarse antes de cambios importantes.

## Ejemplo de `/zephyros/config.json`

Ejemplo sin secretos reales:

```json
{
  "device_id": "zephyros-cardputer-principal",
  "archeion_base_url": "http://192.168.1.50:8000",
  "archeion_device_token": "REEMPLAZAR_CON_TOKEN_LOCAL",
  "timezone": "America/Mexico_City"
}
```

Recomendaciones:

- Usar IP local si `archeion.local` no resuelve.
- Si se usa una IP LAN como `http://192.168.1.50:8000`, agregar esa IP a `ALLOWED_HOSTS`; de lo contrario Django puede responder `400 Bad Request` antes de llegar a la API o validar el token.
- Ejemplo: `ALLOWED_HOSTS=127.0.0.1,localhost,archeion,archeion.local,192.168.1.50`.
- No imprimir el token en pantalla de diagnóstico ni logs persistentes.
- Mantener `device_id` estable para conservar idempotencia.

## Comandos de test y validación

```bash
python manage.py check
python manage.py test chremata
git diff --check
```

## Endpoints principales

Todos los endpoints bajo `/api/` requieren `X-Archeion-Device-Token`.

| Método | Endpoint | Uso |
| --- | --- | --- |
| GET | `/api/device/ping/` | Probar conectividad y token del dispositivo. |
| GET | `/api/v1/catalogos/` | Descargar snapshot de catálogos activos para Zephyros. |
| GET | `/api/v1/chremata/schema/` | Consultar contratos vigentes de sincronización Chremata. |
| GET | `/api/v1/chremata/material-pool/` | Consultar estado consolidado del material pool. |
| GET | `/api/v1/chremata/cajas/<caja_public_id>/corte/` | Consultar corte oficial de una sesión de caja. |
| POST | `/api/v1/chremata/operations/` | Sincronizar operaciones idempotentes desde Zephyros. |

Operaciones Chremata vigentes:

- `crear_ticket`
- `cobrar_ticket`
- `cancelar_ticket`
- `abandonar_ticket`
- `crear_gasto_material`
- `abrir_caja`
- `cerrar_caja`

## Mapa de documentación

- [`docs/arquitectura.md`](docs/arquitectura.md): arquitectura y responsabilidades del sistema.
- [`docs/chremata_api.md`](docs/chremata_api.md): endpoints, contratos e idempotencia de API.
- [`docs/zephyros_sync.md`](docs/zephyros_sync.md): contrato vigente de sincronización offline-first.
- [`docs/manual_operativo.md`](docs/manual_operativo.md): operación diaria y diagnóstico práctico.
- [`docs/despliegue_raspberry.md`](docs/despliegue_raspberry.md): guía inicial para Raspberry; `systemd` final pendiente.
- [`docs/troubleshooting.md`](docs/troubleshooting.md): problemas frecuentes y cómo resolverlos.
- [`docs/decisiones.md`](docs/decisiones.md): decisiones de diseño consolidadas.
- [`docs/seguridad.md`](docs/seguridad.md): tokens de dispositivo y seguridad local.


## Flujo oficial de caja Chremata

1. Antes de consulta, Zephyros abre una caja con `abrir_caja`, generando una `CajaSesion` asociada opcionalmente a una `CajaFisica`.
2. Durante consulta, se pueden crear tickets pendientes sin caja; cobrar un ticket en Zephyros requiere caja abierta y debe enviar `caja_public_id`.
3. Los gastos de material capturados durante la sesión pueden enviar el mismo `caja_public_id`; se reportan aparte en el corte y no reducen el efectivo esperado.
4. Al final, Zephyros cierra la caja con `cerrar_caja`, enviando el efectivo contado. Archeion calcula y guarda el `resumen_snapshot`.
5. Después de sincronizar, comparar el corte local auxiliar de Zephyros contra `GET /api/v1/chremata/cajas/<caja_public_id>/corte/`, que es la autoridad.

El corte oficial incluye `caja`, `efectivo`, `totales`, `totales_por_metodo`, `totales_por_canal`, `totales_por_concepto`, `gastos_material` y `tickets`. Los totales por concepto salen de `TicketLinea`, no del concepto resumen del pago.
