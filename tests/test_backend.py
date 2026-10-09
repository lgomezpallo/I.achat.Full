import iachat.backend as module
from iachat.backend import RouterBackend

class FakeResponse:
    def __init__(self, body, status=200):
        self.body = body
        self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")
    def json(self):
        return self.body

def test_router_backend_returns_text(monkeypatch):
    captured = {}
    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse({"ok": True, "text": "respuesta", "provider": "groq", "model": "x"})
    monkeypatch.setattr(module.httpx, "post", fake_post)
    backend = RouterBackend("http://router:8010", token="service-secret")
    answer = backend.answer([
        {"role":"user","content":"hola"},
        {"role":"assistant","content":"buenas"},
        {"role":"user","content":"seguimos"},
    ])
    assert answer == "respuesta"
    assert captured["url"] == "http://router:8010/route"
    assert captured["headers"]["Authorization"] == "Bearer service-secret"
    assert captured["json"]["task"] == "seguimos"
    assert "assistant: buenas" in captured["json"]["context"]

def test_router_backend_propagates_router_failure(monkeypatch):
    monkeypatch.setattr(module.httpx, "post", lambda *a, **k: FakeResponse({"ok": False, "error": "no_eligible_provider"}))
    backend = RouterBackend("http://router:8010", token="test-token")
    try:
        backend.answer([{"role":"user","content":"hola"}])
        assert False, "expected failure"
    except RuntimeError as exc:
        assert str(exc) == "router_failed"
