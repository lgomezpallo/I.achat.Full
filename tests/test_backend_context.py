from unittest.mock import patch
import pytest

from iachat.backend import RouterBackend


class FakeResponse:
    status_code = 200
    def raise_for_status(self):
        pass

    def json(self):
        return {"ok": True, "text": "Respuesta correcta"}


def test_complete_conversation_is_forwarded_in_order():
    history = [
        {"role": "user", "content": "Me llamo Ana"},
        {"role": "assistant", "content": "Hola Ana"},
        {"role": "user", "content": "¿Cómo me llamo?"},
    ]
    with patch("iachat.backend.httpx.post", return_value=FakeResponse()) as post:
        reply = RouterBackend("http://router:8010", token="test-token").answer(history)
    assert reply == "Respuesta correcta"
    args, kwargs = post.call_args
    assert args[0] == "http://router:8010/route"
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert kwargs["json"]["task"] == "¿Cómo me llamo?"
    assert kwargs["json"]["context"] == "user: Me llamo Ana\nassistant: Hola Ana"
    assert kwargs["json"]["application_name"] == "iachat"
    assert kwargs["json"]["decompose"] is False


def test_last_message_must_be_user():
    with pytest.raises(ValueError, match="last_message_must_be_user"):
        RouterBackend("http://router:8010").answer([
            {"role": "assistant", "content": "Hola"},
        ])
