"""Offline user isolation regression for conversation search."""
import tempfile
from pathlib import Path
from iachat.store import ConversationStore

def test_search_is_owner_scoped():
    with tempfile.TemporaryDirectory() as tmp:
        s = ConversationStore(str(Path(tmp) / "test.db"))
        s.put("a", [{"role": "user", "content": "El contrato de la obra está listo"}], "alice")
        s.put("b", [{"role": "user", "content": "El contrato es privado"}], "bob")
        alice = s.search_conversations("contrato", "alice")
        bob = s.search_conversations("contrato", "bob")
        assert [x["id"] for x in alice] == ["a"]
        assert [x["id"] for x in bob] == ["b"]
        assert not s.search_conversations("privado", "alice")
        assert not s.search_conversations("x", "bob")


def test_project_scoped_history_and_move():
    s = ConversationStore(":memory:")
    s.put("general", [{"role": "user", "content": "Trabajo general"}], "alice")
    s.put("router", [{"role": "user", "content": "Trabajo Router"}], "alice", "Router")
    s.put("iachat", [{"role": "user", "content": "Trabajo IAchat"}], "alice", "IAchat")
    assert {x["id"] for x in s.list_conversations("alice", "")} == {"general"}
    assert {x["id"] for x in s.list_conversations("alice", "Router")} == {"router"}
    assert {x["id"] for x in s.search_conversations("Trabajo", "alice", project="IAchat")} == {"iachat"}
    assert not s.move_conversation("router", "Auditor", "bob")
    assert s.move_conversation("router", "Auditor", "alice")
    assert s.conversation_project("router", "alice") == "Auditor"
    assert s.conversation_project("router", "bob") is None
