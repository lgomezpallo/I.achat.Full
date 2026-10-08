from __future__ import annotations
import os
import hmac
import hashlib
import time
import httpx
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from .store import ConversationStore
from .web import HTML, MANIFEST, SERVICE_WORKER

app = FastAPI(title="IAchat", version="0.3.0")

def _valid_session(value: str) -> bool:
    secret = os.getenv("IACHAT_AUTH_SECRET", "")
    if not secret or not value or "." not in value:
        return False
    expiry, signature = value.split(".", 1)
    if not expiry.isdigit() or int(expiry) < int(time.time()):
        return False
    expected = hmac.new(secret.encode(), expiry.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)

@app.middleware("http")
async def restrict_private_api(request: Request, call_next):
    path = request.url.path
    if os.getenv("IACHAT_PASSWORD") and path.startswith("/api/") and not _valid_session(request.cookies.get("iachat_session", "")):
        return JSONResponse({"detail": "authentication_required"}, status_code=401)
    return await call_next(request)

class LoginInput(BaseModel):
    password: str

@app.post("/auth/login")
def login(payload: LoginInput, response: Response):
    expected = os.getenv("IACHAT_PASSWORD", "")
    secret = os.getenv("IACHAT_AUTH_SECRET", "")
    if not expected or not secret or not hmac.compare_digest(payload.password, expected):
        raise HTTPException(401, "invalid_credentials")
    expiry = str(int(time.time()) + 60 * 60 * 24 * 30)
    signature = hmac.new(secret.encode(), expiry.encode(), hashlib.sha256).hexdigest()
    response.set_cookie("iachat_session", expiry + "." + signature, httponly=True, secure=True, samesite="lax", max_age=2592000)
    return {"ok": True}

@app.get("/auth/status")
def auth_status(request: Request):
    return {"authenticated": _valid_session(request.cookies.get("iachat_session", ""))}

@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie("iachat_session")
    return {"ok": True}

store = ConversationStore(os.getenv("IACHAT_DB", "iachat.db"))

class MessageInput(BaseModel):
    conversation_id: str | None = None
    text: str = Field(min_length=1, max_length=15000)

class MessageOutput(BaseModel):
    conversation_id: str
    answer: str
    history: list[dict[str, str]]

def get_backend():
    from .backend import ProviderBackend
    return ProviderBackend()

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML

@app.get("/manifest.webmanifest")
def manifest():
    return JSONResponse(MANIFEST, media_type="application/manifest+json")

@app.get("/sw.js", response_class=PlainTextResponse)
def service_worker():
    return PlainTextResponse(SERVICE_WORKER, media_type="application/javascript")

@app.get("/health")
def health():
    return {"status": "ok", "component": "iachat", "storage": "sqlite"}

@app.get("/ready")
def ready():
    configured = any(os.getenv(key, "").strip() for key in ("GROQ_API_KEY", "OPENROUTER_API_KEY"))
    if not configured:
        raise HTTPException(503, "providers_not_configured")
    return {"status": "ready", "component": "iachat", "mode": "direct"}

@app.post("/api/chat", response_model=MessageOutput)
def chat(message: MessageInput):
    conversation_id = message.conversation_id or str(uuid4())
    history = store.get(conversation_id)
    if message.conversation_id and history is None:
        raise HTTPException(404, "conversation_not_found")
    history = history or []
    try:
        answer = get_backend().answer([*history, {"role": "user", "content": message.text}])
    except httpx.HTTPStatusError as exc:
        raise HTTPException(503, "providers_http_error") from exc
    except (httpx.RequestError, RuntimeError) as exc:
        detail = str(exc) if isinstance(exc, RuntimeError) else "providers_unavailable"
        if detail not in ("providers_not_configured", "providers_unavailable", "providers_failed"):
            detail = "providers_unavailable"
        raise HTTPException(503, detail) from exc
    updated = [*history, {"role": "user", "content": message.text}, {"role": "assistant", "content": answer}]
    store.put(conversation_id, updated)
    return MessageOutput(conversation_id=conversation_id, answer=answer, history=updated)

@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    history = store.get(conversation_id)
    if history is None:
        raise HTTPException(404, "conversation_not_found")
    return {"conversation_id": conversation_id, "history": history}

@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    if not store.delete(conversation_id):
        raise HTTPException(404, "conversation_not_found")
    return {"deleted": True}
