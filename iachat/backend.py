from __future__ import annotations
import httpx

class GroqBackend:
    def __init__(self, key: str, model: str):
        self.key, self.model = key, model

    def answer(self, messages: list[dict[str, str]]) -> str:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json={"model": self.model, "messages": messages, "temperature": 0.4},
            timeout=45.0,
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("empty_ai_response")
        return answer
