# Despliegue manual de IAchat en Oracle

La acción **Desplegar IAchat en Oracle** se ejecuta únicamente con `workflow_dispatch`: no se dispara con cada commit.

## Preparación de GitHub

1. Repositorio `lgomezpallo/I.achat.Full` → **Settings** → **Environments** → **New environment** → nombre exacto `oracle-production`. Recomendado: activar **Required reviewers** para aprobar cada despliegue.
2. En ese entorno, **Environment secrets** → crear estos cuatro secretos:
   - `ORACLE_HOST`: IP pública o dominio de **la VM actual**, sin `https://` ni puerto.
   - `ORACLE_USER`: nombre del usuario SSH de la VM (habitualmente `ubuntu`).
   - `ORACLE_SSH_KEY`: contenido completo de una **clave privada exclusiva de despliegue**, incluida la cabecera y el pie. **No pegarla en el repositorio ni en chats.**
   - `ORACLE_KNOWN_HOSTS`: línea de `known_hosts` que identifique la clave de host SSH **validada previamente** para esa VM. No confiar ciegamente en un resultado de `ssh-keyscan` sin verificar su huella.
3. La clave pública correspondiente debe estar autorizada en `~/.ssh/authorized_keys` del usuario de la VM. Esto requiere acceso inicial a Oracle. **Subir la clave privada a GitHub no autoriza por sí solo el acceso a Oracle.**
4. Recomendado: crear un usuario de despliegue con permisos limitados en lugar de reutilizar la clave administrativa de la VM. Si se compartió una clave privada fuera del equipo de administración, revocarla/rotarla cuando haya acceso.

## Preparación de Oracle (una vez)

El despliegue usa `rsync`, `tar`, `python`, entorno `.venv` ya existente, y `sudo -n systemctl restart iachat` y `sudo -n systemctl is-active iachat`. Verificar permisos no interactivos de sudo para esas operaciones, sin dar privilegios adicionales.

Ruta esperada: `~/Proyecto/Aplicaciones/IAchat`. Servicio: `iachat.service`. El despliegue toma el puerto local del propio unit (`ExecStart --port`), así que funciona igual con `8000` o `8001`.

Antes de reiniciar, el despliegue crea `/etc/iachat/auth.env` (root:root, 0600) con `IACHAT_AUTH_SECRET` si todavía no existe, y lo carga por systemd junto con las credenciales de Google. Nunca imprime el valor y jamás lo rota: si el archivo existe, se respeta.

### Backend Router (obligatorio)

IAchat no recibe claves de proveedores: toda la inferencia pasa por Router. Crear en la VM `/etc/iachat-router.env` (`root:root`, `0600`) —es el archivo que declara el unit actual—; también se acepta la ruta heredada `/etc/iachat/router.env`:

```ini
ROUTER_URL=http://127.0.0.1:8010
ROUTER_TOKEN=TOKEN_DE_IACHAT
```

El instalador valida permisos, URL loopback y presencia del token **sin imprimir valores**, comprueba `http://127.0.0.1:8010/health` (sin inferencia) y recién entonces reinicia `iachat` con `IACHAT_BACKEND=router`. Si Router no responde o el archivo falta, el despliegue se aborta y se revierte; no vuelve al backend integrado.

## Operación

Un merge a `main` **no despliega**. El orden es:

1. Ejecutar **Router — verificar servicio y puerto 8010 (solo lectura)** y confirmar `PORT_8010_LISTEN=1`, `PORT_8010_NON_LOOPBACK=0`, `ROUTER_HEALTH_HTTP=200` y `ROUTER_AUTH_PROBE=ok_no_inference` (prueba de autenticación con cuerpo inválido, sin ejecutar modelos).
2. Entrar a **Actions** → **Desplegar IAchat en Oracle** → **Run workflow**, rama `main`.

Primero se ejecutan `pytest` y `compileall`. Sólo tras aprobar las pruebas y existir los secretos se intenta conectar a la VM.

El instalador respalda archivos antes de reemplazarlos, preserva `.git`, `.venv` y archivos SQLite, actualiza dependencias, reinicia el servicio y comprueba `/health`. Si falla intenta revertir. **Esto todavía requiere una prueba real**; no equivale a una garantía absoluta de rollback de base de datos o migraciones de esquema.

## Advertencias

- No poner credenciales en `git remote`, commits, tickets o mensajes de chat.
- El sitio web de IAchat y Router tienen credenciales distintas; no modificar sus claves para habilitar este despliegue.
- No se comprueba la inferencia de Router durante la publicación, para evitar gastar cuota. Hacer luego una prueba funcional controlada desde IAchat.
