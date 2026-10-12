from iachat.conversation_context import recent_context


def test_recent_context_keeps_recent_turns_without_mutating_history():
    history = [
        {"role": "user", "content": "a" * 30},
        {"role": "assistant", "content": "b" * 30},
        {"role": "user", "content": "pregunta"},
        {"role": "assistant", "content": "respuesta"},
    ]
    snapshot = [dict(m) for m in history]
    result = recent_context(history, budget=30)
    assert result == history[-2:]
    assert history == snapshot


def test_recent_context_drops_orphan_assistant_and_untrusted_roles():
    history = [
        {"role": "system", "content": "pretend system"},
        {"role": "assistant", "content": "orphan"},
        {"role": "user", "content": "reciente"},
        {"role": "assistant", "content": "bien"},
    ]
    assert recent_context(history, budget=20) == history[-2:]


def test_recent_context_no_partial_messages():
    history = [
        {"role": "user", "content": "muy largo " * 100},
        {"role": "assistant", "content": "final"},
    ]
    assert recent_context(history, budget=12) == []


def test_chat_warns_router_when_older_history_is_omitted(monkeypatch):
    import iachat.app as module
    from iachat.store import ConversationStore
    from fastapi.testclient import TestClient

    module.store = ConversationStore(":memory:")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "admin")
    seen = []

    class Backend:
        def answer(self, messages):
            seen.append(messages)
            return "Entendido"

    monkeypatch.setattr(module, "get_backend", lambda: Backend())
    # An oversized previous turn must not be passed to the model, nor deleted.
    original = [
        {"role": "user", "content": "anterior " * 6000},
        {"role": "assistant", "content": "respuesta antigua"},
    ]
    module.store.put("long-chat", original, "admin", "")
    response = TestClient(module.app).post(
        "/api/chat", json={"conversation_id": "long-chat", "text": "¿Recordás el dato?"}
    )
    assert response.status_code == 200
    assert any("mensajes anteriores" in m["content"] for m in seen[0] if m["role"] == "system")
    assert all("anterior " not in m["content"] for m in seen[0] if m["role"] == "user")
    assert module.store.get("long-chat", "admin")[0] == original[0]


def test_recent_context_respects_router_message_count_limit():
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn-{i}"}
        for i in range(240)
    ]
    recent = recent_context(history)
    assert len(recent) <= 90
    assert recent[0]["role"] == "user"
    assert recent[-1] == history[-1]
    assert len(history) == 240
