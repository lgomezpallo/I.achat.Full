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

Ruta esperada: `~/Proyecto/Aplicaciones/IAchat`. Servicio: `iachat.service`. API local: `127.0.0.1:8000/health`.

## Operación

Entrar a **Actions** → **Desplegar IAchat en Oracle** → **Run workflow**, rama `main`.
Primero se ejecutan `pytest` y `compileall`. Sólo tras aprobar las pruebas y existir los secretos se intenta conectar a la VM.

El instalador respalda archivos antes de reemplazarlos, preserva `.git`, `.venv` y archivos SQLite, actualiza dependencias, reinicia el servicio y comprueba `/health`. Si falla intenta revertir. **Esto todavía requiere una prueba real**; no equivale a una garantía absoluta de rollback de base de datos o migraciones de esquema.

## Advertencias

- No poner credenciales en `git remote`, commits, tickets o mensajes de chat.
- El sitio web de IAchat y Router tienen credenciales distintas; no modificar sus claves para habilitar este despliegue.
- No se comprueba la inferencia de Router durante la publicación, para evitar gastar cuota. Hacer luego una prueba funcional controlada desde IAchat.
