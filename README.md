# IAchat

Chat conversacional independiente de proveedores. Toda inferencia pasa por **Router**; IAchat no conoce modelos ni API keys de proveedores.

## Funciones actuales

- interfaz web responsive e instalable como PWA;
- API conversacional;
- historial persistente en SQLite;
- recuperación y borrado de conversaciones;
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
- `GET /api/conversations/{id}`
- `DELETE /api/conversations/{id}`

## Límite de responsabilidad

IAchat conversa y conserva el hilo. No selecciona proveedores, no administra claves y no implementa lógica de routing. Esa responsabilidad pertenece a Router.
