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
    assert kwargs["trust_env"] is False
    assert kwargs["follow_redirects"] is False


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
        calls.append((kwargs["json"]["application_name"], kwargs["trust_env"]))
        return Response()

    monkeypatch.setattr("iachat.backend.httpx.post", post)
    backend = RouterFirstBackend(url="https://router.example.test", token="test-only")
    assert backend.answer([{"role": "user", "content": "Hola"}]) == "respuesta personal"
    assert calls == [("iachat", True)]


def test_work_instance_cannot_inherit_personal_direct_provider_keys(monkeypatch):
    """An allowlisted model name does not prove the account cannot be billed."""
    import iachat.app as app_module
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.delenv("IACHAT_BACKEND", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "test-key-never-used")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-never-used")
    with pytest.raises(RuntimeError, match="go_router_only_until_free_models_verified"):
        app_module.get_backend()
    from fastapi.testclient import TestClient
    with TestClient(app_module.app, base_url="https://go.test") as client:
        readiness = client.get("/ready")
    assert readiness.status_code == 503
    assert readiness.json()["detail"] == "go_router_only_until_free_models_verified"


def test_work_instance_router_mode_selects_loopback_transport(monkeypatch):
    import iachat.app as app_module
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setenv("IACHAT_BACKEND", "router")
    assert isinstance(app_module.get_backend(), RouterFirstBackend)


def test_personal_instance_can_still_select_integrated_backend(monkeypatch):
    import iachat.app as app_module
    from iachat.backend import ProviderBackend
    monkeypatch.setenv("IACHAT_PROFILE", "personal")
    monkeypatch.setenv("IACHAT_BACKEND", "integrated")
    assert isinstance(app_module.get_backend(), ProviderBackend)
