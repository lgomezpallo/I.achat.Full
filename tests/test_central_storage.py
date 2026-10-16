import pytest
from iachat.central_state import ConversationState, resolve_topic
from iachat.central_storage import CentralStateStore


def test_restart_restores_topic_and_reference(tmp_path):
    path = str(tmp_path / "central.db")
    first = CentralStateStore(path)
    first.save("ana", "chat1", ConversationState(active_topic="Obra 1058", facts={"permiso": "pendiente"}))
    first.close()
    second = CentralStateStore(path)
    state = second.load("ana", "chat1")
    assert state.facts["permiso"] == "pendiente"
    assert resolve_topic("¿Qué pasó ahí?", state).topic == "Obra 1058"
    second.close()


def test_user_and_conversation_isolation(tmp_path):
    store = CentralStateStore(str(tmp_path / "central.db"))
    store.save("ana", "chat1", ConversationState(active_topic="Tema privado"))
    assert store.load("luis", "chat1") is None
    assert store.load("ana", "chat2") is None
    store.save("luis", "chat1", ConversationState(active_topic="Otro tema"))
    assert store.load("ana", "chat1").active_topic == "Tema privado"
    assert store.load("luis", "chat1").active_topic == "Otro tema"
    store.close()


def test_delete_is_owner_scoped(tmp_path):
    store = CentralStateStore(str(tmp_path / "central.db"))
    store.save("ana", "chat1", ConversationState(active_topic="Uno"))
    store.save("luis", "chat1", ConversationState(active_topic="Dos"))
    assert store.delete("ana", "chat1") is True
    assert store.load("ana", "chat1") is None
    assert store.load("luis", "chat1").active_topic == "Dos"
    assert store.delete("ana", "chat1") is False
    store.close()


@pytest.mark.parametrize("owner,conversation", [("", "chat"), ("ana", ""), (None, "chat")])
def test_missing_identity_rejected(tmp_path, owner, conversation):
    store = CentralStateStore(str(tmp_path / "central.db"))
    with pytest.raises(ValueError):
        store.load(owner, conversation)
    store.close()
