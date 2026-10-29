"""Offline regression tests: only explicitly approved free model IDs may be called."""
import pytest

from iachat import backend


@pytest.fixture(autouse=True)
def clean_provider_environment(monkeypatch):
    for name in ("GROQ", "OPENROUTER", "NVIDIA"):
        for suffix in ("API_KEY", "MODELS", "VISION_MODEL"):
            monkeypatch.delenv(f"{name}_{suffix}", raising=False)


def _no_network(*args, **kwargs):
    pytest.fail("Unapproved model attempted an outbound HTTP request")


def test_unapproved_override_cannot_trigger_network(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-offline-key")
    monkeypatch.setenv("GROQ_MODELS", "paid-model,another-paid-model")
    monkeypatch.setattr(backend.httpx, "post", _no_network)
    assert not backend.ProviderBackend.configured()
    with pytest.raises(RuntimeError, match="providers_not_configured"):
        backend.ProviderBackend().answer([{"role": "user", "content": "hola"}])


def test_nvidia_credit_models_disabled_until_free_verified(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-offline-key")
    monkeypatch.setenv("NVIDIA_MODELS", "meta/llama-3.3-70b-instruct")
    monkeypatch.setattr(backend.httpx, "post", _no_network)
    assert not backend.ProviderBackend.configured()
    with pytest.raises(RuntimeError, match="providers_not_configured"):
        backend.ProviderBackend().answer([{"role": "user", "content": "hola"}])


def test_mixed_overrides_only_call_allowlisted_free_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-offline-key")
    monkeypatch.setenv("GROQ_MODELS", "paid-model, openai/gpt-oss-20b, paid-model")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-offline-key")
    monkeypatch.setenv("OPENROUTER_MODELS", "openai/gpt-4o,openai/gpt-oss-20b:free")
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-offline-key")
    sent = []

    class Response:
        status_code = 429

    class GoodResponse:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": "respuesta gratis"}}]}

    def fake_post(url, *, headers, json, timeout):
        sent.append((url, json["model"]))
        return Response() if len(sent) == 1 else GoodResponse()

    monkeypatch.setattr(backend.httpx, "post", fake_post)
    assert backend.ProviderBackend.configured()
    assert backend.ProviderBackend().answer([{"role": "user", "content": "hola"}]) == "respuesta gratis"
    assert [model for _, model in sent] == ["openai/gpt-oss-20b", "openai/gpt-oss-20b:free"]
    assert "api.nvidia.com" not in " ".join(url for url, _ in sent)


def test_vision_override_cannot_bypass_allowlist(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-offline-key")
    monkeypatch.setenv("OPENROUTER_VISION_MODEL", "openai/gpt-4o")
    monkeypatch.setattr(backend.httpx, "post", _no_network)
    with pytest.raises(RuntimeError, match="vision_not_configured"):
        backend.ProviderBackend().answer(
            [{"role": "user", "content": "describí"}], images=["data:image/png;base64,AAAA"]
        )


def test_default_free_models_remain_available(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-offline-key")
    assert backend.ProviderBackend.configured()
    assert backend.ProviderBackend._eligible_models(
        "groq", ("openai/gpt-oss-20b", "llama-3.3-70b-versatile")
    ) == ("openai/gpt-oss-20b", "llama-3.3-70b-versatile")
