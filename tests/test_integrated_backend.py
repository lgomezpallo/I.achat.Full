import pytest
import iachat.backend as backend
import iachat.app as app_module
from iachat.backend import ProviderBackend


def test_integrated_is_default(monkeypatch):
    monkeypatch.delenv("IACHAT_BACKEND", raising=False)
    assert isinstance(app_module.get_backend(), ProviderBackend)


def test_direct_provider_without_router(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    calls = []
    class Response:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": "Hola, ¿cómo estás?"}}]}
    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()
    monkeypatch.setattr(backend.httpx, "post", fake_post)
    answer = ProviderBackend().answer([{"role": "user", "content": "Hola"}])
    assert answer == "Hola, ¿cómo estás?"
    assert calls[0][0] == "https://api.groq.com/openai/v1/chat/completions"
    assert calls[0][1]["json"]["messages"][-1]["content"] == "Hola"


def test_fallback_after_rate_limit(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_MODELS", "openai/gpt-oss-20b")
    monkeypatch.setenv("OPENROUTER_MODELS", "openai/gpt-oss-20b:free")
    seen = []
    class Response:
        def __init__(self, code):
            self.status_code = code
        def json(self):
            return {"choices": [{"message": {"content": "Respuesta alternativa"}}]}
    def fake_post(url, **kwargs):
        seen.append(url)
        return Response(429 if "groq.com" in url else 200)
    monkeypatch.setattr(backend.httpx, "post", fake_post)
    assert ProviderBackend().answer([{"role": "user", "content": "seguimos"}]) == "Respuesta alternativa"
    assert len(seen) == 2


def test_vision_requires_explicit_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_VISION_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="vision_not_configured"):
        ProviderBackend().answer([{"role": "user", "content": "¿Qué ves?"}], images=["data:image/png;base64,AA=="])


def test_retired_or_unavailable_models_use_free_fallbacks(monkeypatch):
    # Matches stale Oracle settings; no retired or paid model may be attempted.
    monkeypatch.setenv("GROQ_MODELS", "openai/gpt-oss-20b,llama-3.3-70b-versatile")
    monkeypatch.setenv("OPENROUTER_MODELS", "dots-studio/dots-3-note-preview:free,openai/gpt-oss-20b:free")
    groq = ProviderBackend._eligible_models(
        "groq", ProviderBackend.PROVIDERS[0][3])
    router = ProviderBackend._eligible_models(
        "openrouter", ProviderBackend.PROVIDERS[1][3])
    assert groq == ("openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b")
    assert router == ("openrouter/free",)
    assert "llama-3.3-70b-versatile" not in groq


def test_stale_free_models_fall_back_without_paid_calls(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_MODELS", "openai/gpt-oss-20b,llama-3.3-70b-versatile")
    monkeypatch.setenv("OPENROUTER_MODELS", "openai/gpt-oss-20b:free")
    attempted = []
    class Response:
        def __init__(self, status):
            self.status_code = status
        def json(self):
            return {"choices": [{"message": {"content": "Respuesta gratuita"}}]}
    def fake_post(url, **kwargs):
        model = kwargs["json"]["model"]
        attempted.append(model)
        return Response(200 if model == "openai/gpt-oss-120b" else 429)
    monkeypatch.setattr(backend.httpx, "post", fake_post)
    answer = ProviderBackend().answer([{"role": "user", "content": "Hola"}])
    assert answer == "Respuesta gratuita"
    assert attempted == ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
    assert all(m in ProviderBackend.FREE_MODEL_ALLOWLIST["groq"] for m in attempted)


def test_openrouter_only_zero_cost_router(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODELS", "openai/gpt-oss-20b:free,openai/gpt-oss-20b")
    models = ProviderBackend._eligible_models(
        "openrouter", ProviderBackend.PROVIDERS[1][3])
    assert models == ("openrouter/free",)
