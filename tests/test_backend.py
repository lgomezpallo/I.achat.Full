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


def test_gateway_502_wakes_router_then_retries(monkeypatch):
    from iachat.backend import RouterFirstBackend
    calls = []
    class Reply:
        def __init__(self, status, body=None):
            self.status_code = status
            self.body = body or {}
        def json(self):
            return self.body
    def fake_post(url, **kwargs):
        calls.append(("post", url))
        return Reply(502) if len([c for c in calls if c[0] == "post"]) == 1 else Reply(200, {"ok": True, "text": "Funciona por Router"})
    def fake_get(url, **kwargs):
        calls.append(("get", url))
        return Reply(200, {"status": "ok"})
    monkeypatch.setattr(module.httpx, "post", fake_post)
    monkeypatch.setattr(module.httpx, "get", fake_get)
    assert RouterFirstBackend("https://router.example", token="x").answer([{"role":"user","content":"Hola"}]) == "Funciona por Router"
    assert [x[0] for x in calls] == ["post", "get", "post"]

def test_gateway_502_does_not_retry_forever(monkeypatch):
    from iachat.backend import RouterFirstBackend
    class Reply:
        status_code = 502
    calls = []
    monkeypatch.setattr(module.httpx, "post", lambda *args, **kwargs: (calls.append("post") or Reply()))
    monkeypatch.setattr(module.httpx, "get", lambda *args, **kwargs: (calls.append("get") or Reply()))
    import pytest
    with pytest.raises(RuntimeError, match="router_http_502"):
        RouterFirstBackend("https://router.example", token="x").answer([{"role":"user","content":"Hola"}])
    assert calls == ["post", "get", "post"]
