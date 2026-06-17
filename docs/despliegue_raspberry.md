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
