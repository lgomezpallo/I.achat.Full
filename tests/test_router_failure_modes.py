"""HTTP-level resilience checks; no production account or external provider is used."""
import httpx
import pytest
from fastapi.testclient import TestClient
import iachat.app as module
from iachat.backend import RouterBackend
from iachat.store import ConversationStore


@pytest.mark.parametrize("case", ["unauthorized", "rate_limit", "bad_gateway", "invalid_json", "empty_answer", "network"])
def test_router_failure_is_non_destructive(monkeypatch, tmp_path, case):
    previous_store = module.store
    try:
        module.store = ConversationStore(str(tmp_path / (case + ".db")))
        module.store.put("existing", [
            {"role": "user", "content": "Mi perro se llama Tango."},
            {"role": "assistant", "content": "Entendido."},
        ], "test", "")
        original = module.store.get("existing", "test")
        monkeypatch.setattr(module, "_signed_user", lambda cookie: "test")
        monkeypatch.setattr(module, "get_backend", lambda: RouterBackend("http://router:8010", token="testing"))
        class Response:
            status_code = {"unauthorized": 401, "rate_limit": 429, "bad_gateway": 502}.get(case, 200)
            def json(self):
                if case == "invalid_json":
                    raise ValueError("invalid json")
                return {"ok": True, "text": "" if case == "empty_answer" else "OK"}
        def fake_post(*args, **kwargs):
            if case == "network":
                raise httpx.ConnectError("connection unavailable")
            return Response()
        monkeypatch.setattr("iachat.backend.httpx.post", fake_post)
        monkeypatch.setattr("iachat.backend.httpx.get", lambda *args, **kwargs: Response())
        response = TestClient(module.app).post("/api/chat", json={
            "conversation_id": "existing", "text": "¿Cómo se llama?"
        })
        assert response.status_code == 503
        # No invented assistant response, but the failed user turn survives.
        assert module.store.get("existing", "test") == [
            *original, {"role": "user", "content": "¿Cómo se llama?"}
        ]
    finally:
        module.store = previous_store
