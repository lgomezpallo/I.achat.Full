# IAchat

Chat conversacional independiente de proveedores. Toda inferencia pasa por **Router**; IAchat no conoce modelos ni API keys de proveedores.

## Funciones actuales

- interfaz web responsive e instalable como PWA;
- API conversacional;
- historial persistente en SQLite;
- recuperación y borrado de conversaciones desde el servidor;
- memoria explícita y editable entre conversaciones;
- conexión exclusiva con Router por HTTP;
- health check;
- tests automáticos y CI.

## Arranque

```sh
python -m pip install -e .
export ROUTER_URL='http://localhost:8010'
export ROUTER_TOKEN='...'
export IACHAT_DB='./iachat.db'
uvicorn iachat.app:app --host 0.0.0.0 --port 8000
```

Abrí `http://localhost:8000`.

## API

- `GET /` — cliente web/PWA
- `GET /health`
- `POST /api/chat`
- `GET /api/conversations` — listado desde SQLite
- `GET /api/conversations/{id}`
- `DELETE /api/conversations/{id}`
- `POST /api/memories/suggest` — sugerencias de recuerdos a partir de `conversation_id` (pasa por Router, no se guarda automáticamente)
- `GET /api/memories` — consultar recuerdos
- `POST /api/memories` — crear un recuerdo (`content`)
- `PUT /api/memories/{id}` — editar recuerdo
- `DELETE /api/memories/{id}` — borrar recuerdo

## Límite de responsabilidad

IAchat conversa y conserva el hilo. No selecciona proveedores, no administra claves y no implementa lógica de routing. Esa responsabilidad pertenece a Router.

## Persistencia real en despliegue

**Importante:** SQLite guarda los datos en el archivo definido por `IACHAT_DB`. El contenedor utiliza `/data/iachat.db`, pero declarar `VOLUME /data` **no crea automáticamente un disco persistente** en el servicio de hosting. Configurar y verificar un volumen/disk persistente montado en `/data`; comprobar la retención de las conversaciones y memorias tras reinicio y redespliegue. Sin volumen persistente el historial y la memoria pueden perderse.

La memoria actual se guarda **explícitamente** desde el panel Memoria de la PWA. No extrae recuerdos automáticamente, ni resume conversaciones, ni promete búsqueda semántica. Hasta 30 recuerdos (máximo 6000 caracteres combinados de contexto) se envían como referencias al Router en cada mensaje. El historial guardado y los recuerdos son entidades independientes.

**Seguridad:** habilitar `IACHAT_PASSWORD` y `IACHAT_AUTH_SECRET` (valor secreto fuerte) y usar HTTPS en producción. El acceso sin configurar contraseña deja las API privadas sin autenticación. Nunca publicar claves ni el archivo SQLite.

## Sugerencias de memoria

Desde el panel de Memoria, abrí una conversación y tocá «Sugerir recuerdos de este chat». IAchat pide a Router que proponga hasta tres datos estables; podés editar, aprobar o descartar. Nada queda registrado sin aprobación. Las sugerencias generadas por IA pueden ser erróneas: revisarlas antes de guardar. Esta función todavía no genera sugerencias automáticamente al terminar cada chat.
