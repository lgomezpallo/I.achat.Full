# IAchat

Chat conversacional con historial por conversación, API FastAPI y adaptador de proveedor aislado.

## Arranque
```sh
python -m pip install -e .
export ROUTER_URL='http://localhost:8010'
uvicorn iachat.app:app --host 0.0.0.0 --port 8000
```

Endpoints: `GET /health`, `POST /api/chat`, `GET /api/conversations/{id}`.

**Estado:** base funcional conectada exclusivamente a Router por HTTP. IAchat no conoce proveedores, modelos ni claves. El historial actual es temporal en memoria y no sobrevive reinicios; la persistencia e interfaz web se incorporan en las siguientes capas. Nunca guardar credenciales en Git.
