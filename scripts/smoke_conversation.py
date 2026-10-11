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

from iachat import app as module
from iachat.store import ConversationStore


class FakeBackend:
    """Deterministic stand-in to verify HTTP, history and context wiring."""
    def answer(self, messages):
        user_text = messages[-1]["content"]
        context = " ".join(m["content"] for m in messages[:-1] if m["role"] == "user")
        if "bicicleta" in user_text.lower():
            return "La bicicleta está en el balcón." if "balcón" in context else "No lo sé."
        return "Entendido."


def run(live: bool = False):
    previous_store = module.store
    previous_backend = module.get_backend
    previous_signed_user = module._signed_user
    with tempfile.TemporaryDirectory(prefix="iachat-smoke-") as directory:
        database = Path(directory) / "isolated.sqlite"
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
                assert len(module.store.get(conversation_id, "smoke")) == 4
                assert previous_store.get(conversation_id, "smoke") is None
                print("PASS: isolated conversation continuity, HTTP flow and persistence")
                print("MODE:", "LIVE ROUTER" if live else "OFFLINE MOCK")
                print("DATA: temporary SQLite, deleted after run")
        finally:
            module.store = previous_store
            module.get_backend = previous_backend
            module._signed_user = previous_signed_user


if __name__ == "__main__":
    live = os.getenv("IACHAT_SMOKE_LIVE") == "1"
    if live and (not os.getenv("ROUTER_URL") or not os.getenv("ROUTER_TOKEN")):
        raise SystemExit("LIVE mode requires ROUTER_URL and ROUTER_TOKEN")
    run(live)
