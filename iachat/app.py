from __future__ import annotations
import os
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from .store import ConversationStore
from .web import HTML, MANIFEST, SERVICE_WORKER

app = FastAPI(title="IAchat", version="0.2.0")
store = ConversationStore(os.getenv("IACHAT_DB", "iachat.db"))

class MessageInput(BaseModel):
    conversation_id: str | None = None
    text: str = Field(min_length=1, max_length=15000)

class MessageOutput(BaseModel):
    conversation_id: str
    answer: str
    history: list[dict[str, str]]

def get_backend():
    from .backend import RouterBackend
    url = os.environ.get("ROUTER_URL", "").strip()
    if not url:
        raise HTTPException(503, "IAchat requiere configurar ROUTER_URL")
    return RouterBackend(base_url=url)

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
    return {"status": "ok", "component": "iachat"}

@app.post("/api/chat", response_model=MessageOutput)
def chat(message: MessageInput):
    conversation_id = message.conversation_id or str(uuid4())
    history = store.get(conversation_id)
    if message.conversation_id and history is None:
        raise HTTPException(404, "conversation_not_found")
    history = history or []
    answer = get_backend().answer([*history, {"role": "user", "content": message.text}])
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
