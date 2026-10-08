from __future__ import annotations
import httpx


class RouterBackend:
    def __init__(self, base_url: str, timeout_s: float = 60.0, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.token = token

    def answer(self, messages: list[dict[str, str]]) -> str:
        if not messages or messages[-1].get("role") != "user":
            raise ValueError("last_message_must_be_user")

        # Mantener los dos lados del diálogo, en orden: no sólo las respuestas
        # del asistente. La última consulta se envía como tarea actual.
        previous = messages[:-1]
        context = "\n".join(
            f"{item['role']}: {item['content']}"
            for item in previous
            if item.get("role") in {"user", "assistant", "system"}
            and isinstance(item.get("content"), str)
        )
        task = messages[-1].get("content", "")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("empty_user_message")

        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        response = httpx.post(
            self.base_url + "/route",
            headers=headers,
            json={
                "task": task,
                "context": context,
                "required_capabilities": ["chat"],
                "requirements": ["Responder como chat conversacional preservando el contexto recibido."],
                "application_name": "iachat",
                "decompose": False,
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
