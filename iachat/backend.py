from __future__ import annotations
import os
import httpx

class RouterFirstBackend:
    """Strict Router transport. Never claim Router success from a direct-provider fallback."""
    def __init__(self, url: str | None = None, token: str | None = None, timeout_s: float = 65.0):
        self.url = url
        self.token = token
        self.timeout_s = timeout_s

    def answer(self, messages: list[dict[str, str]]) -> str:
        if not messages or messages[-1].get("role") != "user":
            raise ValueError("last_message_must_be_user")
        url = (self.url if self.url is not None else os.getenv("ROUTER_URL", "")).strip().rstrip("/")
        token = (self.token if self.token is not None else os.getenv("ROUTER_TOKEN", "")).strip()
        if not url or not token:
            raise RuntimeError("router_not_configured")
        context = "\n".join(
            f"{item['role']}: {item['content']}"
            for item in messages[:-1]
            if item.get("role") in ("user", "assistant", "system")
        )
        try:
            response = httpx.post(
                url + "/route",
                headers={"Authorization": "Bearer " + token},
                json={
                    "task": messages[-1]["content"],
                    "context": context,
                    "required_capabilities": ["chat"],
                    "application_name": "iachat",
                    "decompose": False
                },
                timeout=self.timeout_s,
            )
        except httpx.RequestError as exc:
            raise RuntimeError("router_unavailable") from exc
        if response.status_code in (401, 403):
            raise RuntimeError("router_auth_rejected")
        if response.status_code != 200:
            # HTTP status only; never log request credentials or provider responses.
            raise RuntimeError("router_http_" + str(response.status_code))
        try:
            result = response.json()
        except ValueError as exc:
            raise RuntimeError("router_invalid_response") from exc
        answer = result.get("text")
        if not result.get("ok") or not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("router_failed")
        return answer.strip()


# Backwards-compatible name used by the integration test suite.
RouterBackend = RouterFirstBackend


class ProviderBackend:
    """Direct provider client. Credentials remain server-side."""
    def __init__(self, timeout_s: float = 60.0):
        self.timeout_s = timeout_s

    def answer(self, messages: list[dict[str, str]]) -> str:
        if not messages or messages[-1].get("role") != "user":
            raise ValueError("last_message_must_be_user")
        providers = [
            ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1",
             ["openai/gpt-oss-20b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]),
            ("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1",
             ["openai/gpt-oss-20b:free", "meta-llama/llama-3.3-70b-instruct:free"]),
        ]
        attempted = False
        temporary_failure = False
        for name, env, base, defaults in providers:
            key = os.getenv(env, "").strip()
            if not key:
                continue
            attempted = True
            custom = os.getenv(name.upper() + "_MODELS", "").strip()
            models = [x.strip() for x in custom.split(",") if x.strip()] if custom else defaults
            for model in models:
                try:
                    response = httpx.post(
                        base + "/chat/completions",
                        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                        json={"model": model, "messages": [
                            {"role": "system", "content": "Sos IAchat. Respondé con claridad, en el idioma del usuario, respetando el contexto."},
                            *messages,
                        ], "stream": False},
                        timeout=self.timeout_s,
                    )
                    if response.status_code in (401, 403):
                        # Invalid credentials: no value is ever logged or sent to the client.
                        break
                    if response.status_code in (408, 429, 500, 502, 503, 504):
                        temporary_failure = True
                        continue
                    if response.status_code >= 400:
                        continue
                    result = response.json()
                    answer = result["choices"][0]["message"]["content"]
                    if isinstance(answer, str) and answer.strip():
                        return answer.strip()
                except (httpx.RequestError, ValueError, KeyError, IndexError, TypeError):
                    temporary_failure = True
                    continue
        if not attempted:
            raise RuntimeError("providers_not_configured")
        if temporary_failure:
            raise RuntimeError("providers_unavailable")
        raise RuntimeError("providers_failed")
