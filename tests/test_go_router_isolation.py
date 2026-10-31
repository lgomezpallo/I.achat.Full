"""Router transport isolation for the shared IAchat / G.O. engine."""
import pytest

from iachat.backend import RouterFirstBackend


def test_go_profile_routes_with_labor_identity_on_oracle_loopback(monkeypatch):
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {"ok": True, "text": "respuesta laboral"}

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr("iachat.backend.httpx.post", post)
    backend = RouterFirstBackend(url="http://127.0.0.1:8010", token="test-only")
    assert backend.answer([{"role": "user", "content": "Hola G.O."}]) == "respuesta laboral"
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == "http://127.0.0.1:8010/route"
    assert kwargs["json"]["application_name"] == "go-ute"
    assert kwargs["json"]["task"] == "Hola G.O."


@pytest.mark.parametrize("url", [
    "https://router.example.test",
    "http://127.0.0.1:8011",
    "http://oracle.example.test:8010",
    "http://localhost:8010/route",
])
def test_go_profile_rejects_non_loopback_router_before_network(monkeypatch, url):
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")

    def unexpected_network(*args, **kwargs):
        pytest.fail("Router request must not leave the Oracle loopback")

    monkeypatch.setattr("iachat.backend.httpx.post", unexpected_network)
    with pytest.raises(RuntimeError, match="go_router_requires_local_endpoint"):
        RouterFirstBackend(url=url, token="test-only").answer(
            [{"role": "user", "content": "No enviar a destino externo"}]
        )


def test_personal_profile_preserves_router_application_identity(monkeypatch):
    monkeypatch.setenv("IACHAT_PROFILE", "personal")
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {"ok": True, "text": "respuesta personal"}

    def post(url, **kwargs):
        calls.append(kwargs["json"]["application_name"])
        return Response()

    monkeypatch.setattr("iachat.backend.httpx.post", post)
    backend = RouterFirstBackend(url="https://router.example.test", token="test-only")
    assert backend.answer([{"role": "user", "content": "Hola"}]) == "respuesta personal"
    assert calls == ["iachat"]
