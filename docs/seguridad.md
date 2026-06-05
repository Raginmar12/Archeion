# Seguridad local de CodexHub

## Tokens de dispositivo

Las rutas bajo `/api/` requieren autenticación mediante el encabezado
`X-Codex-Device-Token`. Cada Cardputer, script local o módulo satélite debe usar su
propio token para poder desactivarlo sin afectar a los demás dispositivos.

Los tokens se crean exclusivamente desde terminal:

```bash
python manage.py crear_device_token "Cardputer principal"
python manage.py crear_device_token "Cardputer principal" --notas "Cardputer Adv"
```

El token completo se muestra una sola vez durante su creación y no se puede recuperar
después. CodexHub guarda únicamente su hash SHA-256 y un prefijo identificador; nunca
guarda el token completo en texto plano.

Desde Django admin se pueden consultar los tokens, editar su nombre y notas, revisar su
último uso y desactivarlos o reactivarlos. No es posible crear tokens desde admin ni
editar manualmente su hash o prefijo.

Mientras exista, `CODEX_DEVICE_TOKEN` funciona únicamente como fallback temporal o de
emergencia cuando no hay ningún token activo en la base de datos. Si hay al menos un
token activo, la API exige un token activo de base de datos y no acepta el fallback.

CodexHub es un sistema local-first y no debe exponerse directamente a internet. Si en el
futuro se requiere acceso remoto, debe utilizarse una red privada como Tailscale,
WireGuard u otra VPN, sin abrir puertos públicos directamente hacia CodexHub.
