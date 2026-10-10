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
