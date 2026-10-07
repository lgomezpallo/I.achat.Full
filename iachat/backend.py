from __future__ import annotations
import httpx

class RouterBackend:
    def __init__(self, base_url: str, timeout_s: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def answer(self, messages: list[dict[str, str]]) -> str:
        context_parts: list[str] = []
        task = ""
        for message in messages:
            role = message.get("role", "")
            content = message.get("content", "")
            if role == "user":
                task = content
            else:
                context_parts.append(f"{role}: {content}")
        response = httpx.post(
            self.base_url + "/route",
            json={
                "task": task,
                "context": "\n".join(context_parts),
                "required_capabilities": ["chat"],
                "requirements": ["Responder como chat conversacional preservando el contexto recibido."],
            },
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("error") or "router_failed")
        answer = data.get("text")
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("empty_router_response")
        return answer
