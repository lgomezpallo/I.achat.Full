"""Router transport isolation for the shared IAchat / G.O. engine."""
import pytest

from iachat.backend import RouterFirstBackend


def test_go_profile_routes_with_labor_identity_on_oracle_loopback(monkeypatch):
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setenv("GO_ROUTER_INFERENCE_ENABLED", "1")
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


def test_go_profile_rejects_unverified_inference_before_network(monkeypatch):
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.delenv("GO_ROUTER_INFERENCE_ENABLED", raising=False)
    monkeypatch.setattr(
        "iachat.backend.httpx.post",
        lambda *a, **kw: pytest.fail("No Router inference before explicit activation"),
    )
    with pytest.raises(RuntimeError, match="go_router_inference_not_authorized"):
        RouterFirstBackend(url="http://127.0.0.1:8010", token="test-only").answer(
            [{"role": "user", "content": "No facturar"}]
        )


def test_go_profile_ready_and_status_fail_closed_without_activation(monkeypatch):
    from fastapi.testclient import TestClient
    import iachat.app as app_module
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setenv("IACHAT_BACKEND", "router")
    monkeypatch.setenv("ROUTER_URL", "http://127.0.0.1:8010")
    monkeypatch.setenv("ROUTER_TOKEN", "test-only")
    monkeypatch.delenv("GO_ROUTER_INFERENCE_ENABLED", raising=False)
    monkeypatch.setattr(app_module, "_signed_user", lambda _: "worker")
    monkeypatch.setattr(
        app_module.httpx, "get",
        lambda *a, **kw: pytest.fail("Status must not probe Router when locked"),
    )
    with TestClient(app_module.app, base_url="https://go.test") as client:
        readiness = client.get("/ready")
        status = client.get("/api/router/status")
    assert readiness.status_code == 503
    assert readiness.json()["detail"] == "go_router_inference_not_authorized"
    assert status.status_code == 200
    assert status.json()["reason"] == "go_router_inference_not_authorized"
    assert status.json()["routing_verified"] is False


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


def test_work_router_status_rejects_remote_endpoint_without_network(monkeypatch):
    from fastapi.testclient import TestClient
    import iachat.app as app_module
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setenv("IACHAT_BACKEND", "router")
    monkeypatch.setenv("ROUTER_URL", "https://external.example.test")
    monkeypatch.setenv("ROUTER_TOKEN", "test-only")
    monkeypatch.setattr(app_module, "_signed_user", lambda _: "worker")

    def no_network(*args, **kwargs):
        pytest.fail("No network access to a remote Router from G.O.")

    monkeypatch.setattr(app_module.httpx, "get", no_network)
    with TestClient(app_module.app, base_url="https://go.test") as client:
        readiness = client.get("/ready")
        status = client.get("/api/router/status")
    assert readiness.status_code == 503
    assert readiness.json()["detail"] == "go_router_requires_local_endpoint"
    assert status.status_code == 200
    assert status.json()["reason"] == "go_router_requires_local_endpoint"
    assert status.json()["reachable"] is False


def test_work_router_health_uses_no_proxy_and_never_claims_inference(monkeypatch):
    from fastapi.testclient import TestClient
    import iachat.app as app_module
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setenv("GO_ROUTER_INFERENCE_ENABLED", "1")
    monkeypatch.setenv("IACHAT_BACKEND", "router")
    monkeypatch.setenv("ROUTER_URL", "http://127.0.0.1:8010")
    monkeypatch.setenv("ROUTER_TOKEN", "test-only")
    monkeypatch.setattr(app_module, "_signed_user", lambda _: "worker")
    calls = []

    class Health:
        status_code = 200
        def json(self):
            return {"status": "ok"}

    def health(url, **kwargs):
        calls.append((url, kwargs))
        return Health()

    monkeypatch.setattr(app_module.httpx, "get", health)
    with TestClient(app_module.app, base_url="https://go.test") as client:
        readiness = client.get("/ready")
        status = client.get("/api/router/status")
    assert readiness.status_code == 200
    assert status.status_code == 200
    assert status.json()["reachable"] is True
    assert status.json()["routing_verified"] is False
    assert readiness.json()["routing_verified"] is False
    assert calls == [("http://127.0.0.1:8010/health",
                      {"timeout": 8.0, "follow_redirects": False, "trust_env": False})] * 2


def test_work_readiness_rejects_unreachable_router_even_when_opted_in(monkeypatch):
    """No false HTTP 200 readiness just because the feature flag is enabled."""
    from fastapi.testclient import TestClient
    import iachat.app as app_module
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setenv("GO_ROUTER_INFERENCE_ENABLED", "1")
    monkeypatch.setenv("IACHAT_BACKEND", "router")
    monkeypatch.setenv("ROUTER_URL", "http://127.0.0.1:8010")
    monkeypatch.setenv("ROUTER_TOKEN", "test-only")
    monkeypatch.setattr(app_module, "_signed_user", lambda _: "worker")

    def unavailable(url, **kwargs):
        assert url == "http://127.0.0.1:8010/health"
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        raise app_module.httpx.ConnectError("unreachable")

    monkeypatch.setattr(app_module.httpx, "get", unavailable)
    with TestClient(app_module.app, base_url="https://go.test") as client:
        readiness = client.get("/ready")
        status = client.get("/api/router/status")
    assert readiness.status_code == 503
    assert readiness.json()["detail"] == "router_unavailable"
    assert status.json()["reachable"] is False
    assert status.json()["routing_verified"] is False


@pytest.mark.parametrize("gateway_status", [502, 503, 504])
def test_go_profile_never_retries_route_after_gateway_error(monkeypatch, gateway_status):
    """One labor request means one Router dispatch, even on a gateway outage.

    Router owns per-model fallback. Retrying /route at the client could
    consume another free-tier request and duplicate a work prompt.
    """
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setenv("GO_ROUTER_INFERENCE_ENABLED", "1")
    calls = []

    class GatewayResponse:
        status_code = gateway_status

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return GatewayResponse()

    monkeypatch.setattr("iachat.backend.httpx.post", fake_post)
    monkeypatch.setattr(
        "iachat.backend.httpx.get",
        lambda *args, **kwargs: pytest.fail("G.O. must not wake/retry Router"),
    )
    backend = RouterFirstBackend(url="http://127.0.0.1:8010", token="test-only")
    with pytest.raises(RuntimeError, match=rf"^router_http_{gateway_status}$"):
        backend.answer([{"role": "user", "content": "Novedad laboral de prueba"}])
    assert len(calls) == 1
    assert calls[0][0] == "http://127.0.0.1:8010/route"
    assert calls[0][1]["json"]["application_name"] == "go-ute"
