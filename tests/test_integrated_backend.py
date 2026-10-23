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
    monkeypatch.setenv("GROQ_MODELS", "one")
    monkeypatch.setenv("OPENROUTER_MODELS", "two")
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
