"""Isolated conversation smoke test; never accesses production SQLite or accounts.

Run offline: python scripts/smoke_conversation.py
Run with actual Router (quota-consuming):
    IACHAT_SMOKE_LIVE=1 ROUTER_URL=... ROUTER_TOKEN=... python scripts/smoke_conversation.py
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from iachat.store import ConversationStore


class FakeBackend:
    """Deterministic stand-in to verify HTTP, history and context wiring."""
    def answer(self, messages):
        user_text = messages[-1]["content"]
        context = " ".join(m["content"] for m in messages[:-1] if m["role"] == "user")
        if "palabra clave de prueba" in user_text.lower():
            return "luciérnaga" if any("luciérnaga" in m.get("content", "").lower() for m in messages if m["role"] == "system") else "No lo sé."
        if "marca" in user_text.lower():
            return "No me dijiste la marca." if "marca" not in context.lower() else "Ya mencionaste una marca."
        if "bicicleta" in user_text.lower():
            return "La bicicleta está en el balcón." if "balcón" in context else "No lo sé."
        return "Entendido."


def run(live: bool = False):
    with tempfile.TemporaryDirectory(prefix="iachat-smoke-") as directory:
        database = Path(directory) / "isolated.sqlite"
        old_db_setting = os.environ.get("IACHAT_DB")
        os.environ["IACHAT_DB"] = str(database)
        from iachat import app as module
        previous_store = module.store
        previous_backend = module.get_backend
        previous_signed_user = module._signed_user
        module.store = ConversationStore(str(database))
        module.store.create_user("smoke", "temporary-only-password")
        module._signed_user = lambda cookie: "smoke"
        if not live:
            module.get_backend = lambda: FakeBackend()
        try:
            with TestClient(module.app) as client:
                first = client.post("/api/chat", json={
                    "text": "Tengo una bicicleta azul. La guardo en el balcón."
                })
                assert first.status_code == 200, f"initial chat HTTP {first.status_code}"
                payload = first.json()
                conversation_id = payload["conversation_id"]
                second = client.post("/api/chat", json={
                    "conversation_id": conversation_id,
                    "text": "¿Dónde guardo mi bicicleta?"
                })
                assert second.status_code == 200, f"follow-up HTTP {second.status_code}"
                answer = second.json()["answer"].casefold()
                assert "balc" in answer, f"continuity failure: {answer[:150]!r}"
                unknown = client.post("/api/chat", json={
                    "conversation_id": conversation_id,
                    "text": "¿De qué marca es mi bicicleta?"
                })
                assert unknown.status_code == 200
                unknown_answer = unknown.json()["answer"].casefold()
                if live:
                    assert not any(x in unknown_answer for x in ("trek", "giant", "specialized", "venzo", "scott")), "invented bicycle brand"
                    assert any(x in unknown_answer for x in ("no ", "nunca", "desconozco", "sin información", "no tengo")), "model failed to acknowledge unknown brand"
                else:
                    assert "no me dijiste" in unknown_answer
                other = client.post("/api/chat", json={
                    "text": "¿Dónde guardo mi bicicleta?"
                })
                assert other.status_code == 200
                other_answer = other.json()["answer"].casefold()
                if live:
                    # Synthetic data only. Print precisely what the model said, to
                    # distinguish hypothetical examples from claimed user memory.
                    print("ISOLATION_ANSWER:", repr(other_answer[:700]), flush=True)
                    print("ISOLATION_NEW_CHAT:", other.json()["conversation_id"] != conversation_id, flush=True)
                    assert not any(
                        phrase in other_answer for phrase in
                        ("la guardás en el balcón", "la guardas en el balcón",
                         "la guardo en el balcón", "tu bicicleta está en el balcón")
                    ), "model asserts an unprovided location in a separate conversation"
                else:
                    assert other.json()["answer"] == "No lo sé."
                assert other.json()["conversation_id"] != conversation_id
                assert len(module.store.get(conversation_id, "smoke")) == 6
                # Cross-conversation explicit memory test: user saves a fact,
                # then asks in a fresh chat. This tests the actual persisted
                # memory injection path, independently of transcript history.
                saved = client.post("/api/chat", json={
                    "text": "Recordá que mi palabra clave de prueba es luciérnaga."
                })
                assert saved.status_code == 200
                remembered = client.post("/api/chat", json={
                    "text": "¿Cuál es mi palabra clave de prueba? Respondé sólo la palabra."
                })
                assert remembered.status_code == 200
                if live:
                    print("MEMORY_ANSWER:", repr(remembered.json()["answer"][:300]), flush=True)
                assert "luci" in remembered.json()["answer"].casefold(), "saved memory was not recalled"
                assert remembered.json()["conversation_id"] != saved.json()["conversation_id"]
                # Real long-history retrieval: many short turns displace the
                # original fact from the recent message-count window.
                long_id = "smoke-long-history"
                long_history = [
                    {"role": "user", "content": "Mi vehículo de prueba es un coche color turquesa."},
                    {"role": "assistant", "content": "Entendido."},
                ]
                for index in range(120):
                    long_history.extend([
                        {"role": "user", "content": f"Mensaje de relleno número {index}."},
                        {"role": "assistant", "content": "Recibido."},
                    ])
                module.store.put(long_id, long_history, "smoke", "")
                long_response = client.post("/api/chat", json={
                    "conversation_id": long_id,
                    "text": "¿De qué color es mi auto de prueba?"
                })
                assert long_response.status_code == 200
                if live:
                    print("LONG_CONTEXT_ANSWER:", repr(long_response.json()["answer"][:300]), flush=True)
                assert "turquesa" in long_response.json()["answer"].casefold(), "older conversation fact not recovered"
                assert len(module.store.get(long_id, "smoke")) == len(long_history) + 2
                assert module.store is not previous_store
                print("PASS: isolated continuity, unknown facts, conversation isolation and persistence")
                print("MODE:", "LIVE ROUTER" if live else "OFFLINE MOCK")
                print("DATA: temporary SQLite, deleted after run")
        finally:
            module.store = previous_store
            module.get_backend = previous_backend
            module._signed_user = previous_signed_user
            if old_db_setting is None:
                os.environ.pop("IACHAT_DB", None)
            else:
                os.environ["IACHAT_DB"] = old_db_setting


if __name__ == "__main__":
    live = os.getenv("IACHAT_SMOKE_LIVE") == "1"
    if live and (not os.getenv("ROUTER_URL") or not os.getenv("ROUTER_TOKEN")):
        raise SystemExit("LIVE mode requires ROUTER_URL and ROUTER_TOKEN")
    run(live)
