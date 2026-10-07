# IAchat

Chat conversacional con historial por conversación, API FastAPI y adaptador de proveedor aislado.

## Arranque
```sh
python -m pip install -e .
export IACHAT_API_KEY='tu_clave'
uvicorn iachat.app:app --host 0.0.0.0 --port 8000
```

Endpoints: `GET /health`, `POST /api/chat`, `GET /api/conversations/{id}`.

**Estado:** base inicial funcional. El historial es temporal en memoria y no sobrevive reinicios. No existe aún interfaz web ni integración definitiva con Router. El backend Groq es un adaptador provisional, no una dependencia de la API de IAchat. Nunca guardar credenciales en Git.
