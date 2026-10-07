from __future__ import annotations
import os
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="IAchat", version="0.1.0")
sessions: dict[str, list[dict[str, str]]] = {}

class MessageInput(BaseModel):
    conversation_id: str | None = None
    text: str = Field(min_length=1, max_length=15000)

class MessageOutput(BaseModel):
    conversation_id: str
    answer: str
    history: list[dict[str, str]]

def get_backend():
    from .backend import GroqBackend
    key = os.environ.get("IACHAT_API_KEY", "")
    if not key:
        raise HTTPException(503, "IAchat requiere configurar IACHAT_API_KEY")
    return GroqBackend(key=key, model=os.getenv("IACHAT_MODEL", "llama-3.3-70b-versatile"))

@app.get("/health")
def health():
    return {"status": "ok", "component": "iachat"}

@app.post("/api/chat", response_model=MessageOutput)
def chat(message: MessageInput):
    conversation_id = message.conversation_id or str(uuid4())
    if message.conversation_id and conversation_id not in sessions:
        raise HTTPException(404, "conversation_not_found")
    history = sessions.get(conversation_id, [])
    answer = get_backend().answer([*history, {"role": "user", "content": message.text}])
    updated = [*history, {"role": "user", "content": message.text}, {"role": "assistant", "content": answer}]
    sessions[conversation_id] = updated
    return MessageOutput(conversation_id=conversation_id, answer=answer, history=updated)

@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    if conversation_id not in sessions:
        raise HTTPException(404, "conversation_not_found")
    return {"conversation_id": conversation_id, "history": sessions[conversation_id]}
