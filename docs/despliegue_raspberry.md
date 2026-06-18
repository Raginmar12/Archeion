# Despliegue en Raspberry

## Estado

Pendiente de terminar y formalizar el despliegue final. Esta guía documenta el camino inicial probado/esperado, pero los detalles definitivos de `systemd`, usuario de servicio, rutas de logs y respaldos quedan pendientes.

Archeion no debe exponerse directamente a internet. Usar solo red local o una VPN privada si en el futuro se requiere acceso remoto.

## Clonar repo

```bash
git clone <URL_DEL_REPOSITORIO> archeion
cd archeion
```

## Crear entorno virtual

```bash
python -m venv .venv
source .venv/bin/activate
```

## Instalar requirements

```bash
pip install -r requirements.txt
```

## Crear `/etc/archeion.env`

Ejemplo sin secretos reales:

```bash
DJANGO_SETTINGS_MODULE=archeion.settings
ALLOWED_HOSTS=127.0.0.1,localhost,archeion,archeion.local,192.168.1.50
# SECRET_KEY=definir_fuera_del_repositorio_si_se_formaliza_produccion
# DEBUG=False cuando se formalice despliegue no-dev
```

La variable `ALLOWED_HOSTS` debe incluir el hostname o la IP fija/reservada que Zephyros usa en `archeion_base_url`; por ejemplo, la IP LAN de la Raspberry.

Pendiente: definir variables finales requeridas para el servicio permanente.

## Migrar

```bash
python manage.py migrate
```
## Recolectar archivos estáticos

Después de instalar dependencias y aplicar migraciones, recolectar los archivos estáticos para que WhiteNoise pueda servir el CSS/JS de Django Admin cuando Archeion corre con Gunicorn/systemd:

```bash
python manage.py collectstatic --noinput
```

Este comando genera el directorio `staticfiles/` local, que está ignorado por Git y no debe commitearse. Ejecutarlo antes de iniciar o reiniciar el servicio.


## Ejecutar seed inicial

Solo sobre base limpia:

```bash
python manage.py seed_chremata_catalogs
```

## Crear token de Zephyros

```bash
python manage.py crear_device_token "Zephyros"
```

Copiar el token al dispositivo sin guardarlo en el repositorio.

## Probar con `runserver`

```bash
python manage.py runserver 0.0.0.0:8000
```

Configurar Zephyros con:

```json
{
  "archeion_base_url": "http://IP_DE_RASPBERRY:8000"
}
```

## Probar con `gunicorn`

Si `gunicorn` está instalado y configurado:

```bash
gunicorn archeion.wsgi:application --bind 0.0.0.0:8000
```

Pendiente: definir configuración definitiva de workers, usuario y logs.



Cuando el servicio `systemd` ya exista, reiniciarlo después de actualizar código, instalar dependencias, migrar y ejecutar `collectstatic`:

```bash
sudo systemctl restart archeion
```

## Preparar futuro `systemd`

Pendiente de formalizar:

- Usuario dedicado.
- Working directory.
- Archivo EnvironmentFile apuntando a `/etc/archeion.env`.
- Comando `gunicorn` definitivo.
- Restart policy.
- Logs.
- Procedimiento de actualización.

## Seguridad de red

- No abrir puertos públicos hacia Archeion.
- Preferir red local confiable.
- Para acceso remoto futuro, usar VPN privada como Tailscale o WireGuard.
- Rotar token si se sospecha exposición.


## Operación diaria en Raspberry

Cuando Archeion corra en Raspberry, el flujo operativo no cambia: Zephyros abre caja antes de cobrar, sincroniza operaciones, cierra caja al final y consulta el corte oficial en Archeion con `GET /api/v1/chremata/cajas/<caja_public_id>/corte/`.

La Raspberry hospeda la autoridad de datos; el corte local de Zephyros sigue siendo auxiliar. Respaldar la base antes de mantenimientos importantes, especialmente después de sesiones con caja cerrada y `resumen_snapshot` persistido.

## Troubleshooting de archivos estáticos

Si el Django Admin carga sin formato, sin CSS o sin JavaScript, revisar:

- Que `whitenoise` esté instalado en el entorno virtual activo.
- Que `python manage.py collectstatic --noinput` se haya ejecutado después de instalar dependencias.
- Que el servicio se haya reiniciado con `sudo systemctl restart archeion`.
- Que exista el directorio configurado como `STATIC_ROOT` (`staticfiles/`).