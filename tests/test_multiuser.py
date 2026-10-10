from iachat.store import ConversationStore

def test_users_and_private_data(tmp_path):
    db = ConversationStore(str(tmp_path / "multiuser.sqlite"))
    assert db.create_user("admin", "a-secret-password", admin=True)
    assert db.create_user("user2", "another-secret-password")
    assert db.verify_user("admin", "a-secret-password")
    assert not db.verify_user("user2", "a-secret-password")
    db.put("id1", [{"role": "user", "content": "privado"}], owner="admin")
    assert db.get("id1", "admin") is not None
    assert db.get("id1", "user2") is None
    assert db.list_conversations("user2") == []
    db.save_memory("memo1", "secreto", owner="admin")
    assert db.list_memories("user2") == []
    assert not db.delete("id1", "user2")
    assert not db.delete_memory("memo1", "user2")
    assert db.get("id1", "admin") is not None
    assert db.set_enabled("user2", False)
    assert not db.verify_user("user2", "another-secret-password")
    assert not db.set_enabled("admin", False)
