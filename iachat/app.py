from __future__ import annotations
import os
import hmac
import hashlib
import time
import httpx
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response as RawResponse
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
    from .backend import RouterFirstBackend
    return RouterFirstBackend()

@app.on_event("startup")
def check_router_on_startup():
    # Probe the real application path without exposing credentials or response content.
    import threading
    def probe():
        try:
            get_backend().answer([{"role": "user", "content": "Respondé únicamente OK."}])
            print("IACHAT_ROUTER_PROBE status=ok", flush=True)
        except Exception as exc:
            reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
            if reason not in {"router_not_configured", "router_auth_rejected", "router_unavailable",
                              "router_http_error", "router_invalid_response", "router_failed"}:
                reason = "unexpected_error"
            print(f"IACHAT_ROUTER_PROBE status=failed reason={reason}", flush=True)
    threading.Thread(target=probe, daemon=True).start()

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML

def _pwa_icon(size: int) -> bytes:
    import struct
    import zlib
    from functools import lru_cache
    # Self-contained PNG icons: no asset hosting, extra libraries or binary commits.
    bg = (16, 21, 30)
    panel = (48, 67, 99)
    blue = (117, 155, 247)
    glyphs = {
        "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
        "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001")
    }
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            u, v = x / size, y / size
            cx = max(.18-u, 0, u-.82)
            cy = max(.18-v, 0, v-.82)
            col = panel if cx*cx+cy*cy < .13*.13 else bg
            # IA monogram rendered into a unified 11x7 pixel glyph grid.
            gx = int((u-.255)/.045)
            gy = int((v-.345)/.045)
            if 0 <= gy < 7 and 0 <= gx < 11:
                if gx < 5 and glyphs["I"][gy][gx] == "1":
                    col = blue
                if gx >= 6 and glyphs["A"][gy][gx-6] == "1":
                    col = blue
            row.extend(col)
        rows.append(b"\x00" + bytes(row))
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name+data)&0xffffffff)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 6))
            + chunk(b"IEND", b""))

@app.get("/icons/icon-{size}.png")
def pwa_icon(size: int):
    if size not in (192, 512):
        raise HTTPException(404, "icon_not_found")
    return RawResponse(_pwa_icon(size), media_type="image/png",
                       headers={"Cache-Control": "public, max-age=86400"})

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
    if not os.getenv("ROUTER_URL", "").strip() or not os.getenv("ROUTER_TOKEN", "").strip():
        raise HTTPException(503, "router_not_configured")
    return {"status": "ready", "component": "iachat", "mode": "router_only", "router_configured": True}

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
        if detail not in ("router_not_configured", "router_auth_rejected", "router_unavailable", "router_http_error", "router_invalid_response", "router_failed"):
            detail = "router_unavailable"
        raise HTTPException(503, detail) from exc
    updated = [*history, {"role": "user", "content": message.text}, {"role": "assistant", "content": answer}]
    store.put(conversation_id, updated)
    return MessageOutput(conversation_id=conversation_id, answer=answer, history=updated)

@app.get("/api/conversations")
def list_conversations():
    return {"conversations": store.list_conversations()}

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
