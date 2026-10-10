"""Project-scoped memory remains isolated and old data stays general."""
import sqlite3
from fastapi.testclient import TestClient
import iachat.app as module
from iachat.store import ConversationStore


def test_migration_keeps_existing_memories_general(tmp_path):
    db = str(tmp_path / "legacy.db")
    old = sqlite3.connect(db)
    old.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, content TEXT NOT NULL, updated_at INTEGER NOT NULL, owner TEXT NOT NULL DEFAULT 'admin')")
    old.execute("INSERT INTO memories VALUES ('old', 'Siempre en español', 1, 'admin')")
    old.commit()
    old.close()
    store = ConversationStore(db)
    assert store.list_memories("admin", "Router")[0]["content"] == "Siempre en español"
    assert store.list_memories("admin", "Router")[0]["project"] == ""


def test_project_memories_do_not_leak_between_projects():
    store = ConversationStore(":memory:")
    store.save_memory("global", "Siempre en español", "admin")
    store.save_memory("router", "Preferir modelos Groq", "admin", "Router")
    store.save_memory("iachat", "Historial visible", "admin", "IAchat")
    router = [m["content"] for m in store.list_memories("admin", "Router")]
    iachat = [m["content"] for m in store.list_memories("admin", "IAchat")]
    general = [m["content"] for m in store.list_memories("admin", "")]
    assert set(router) == {"Siempre en español", "Preferir modelos Groq"}
    assert set(iachat) == {"Siempre en español", "Historial visible"}
    assert general == ["Siempre en español"]
    assert store.list_memories("other", "Router") == []


def test_router_receives_only_selected_project_memories(monkeypatch):
    module.store = ConversationStore(":memory:")
    module.store.save_memory("global", "Siempre en español", "admin")
    module.store.save_memory("router", "Usar Groq", "admin", "Router")
    module.store.save_memory("iachat", "Guardar historial", "admin", "IAchat")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "admin")
    captured = []
    class Backend:
        def answer(self, messages):
            captured.append(messages)
            return "OK"
    monkeypatch.setattr(module, "get_backend", lambda: Backend())
    client = TestClient(module.app)
    result = client.post("/api/chat", json={"text": "Hola", "project": "Router"})
    assert result.status_code == 200
    context = captured[0][0]["content"]
    assert "Siempre en español" in context
    assert "Usar Groq" in context
    assert "Guardar historial" not in context
    result = client.post("/api/chat", json={"text": "Hola", "project": "IAchat"})
    assert result.status_code == 200
    assert "Guardar historial" in captured[1][0]["content"]
    assert "Usar Groq" not in captured[1][0]["content"]
