"""HTTP-level authorization regression tests, using only disposable SQLite data."""
from fastapi.testclient import TestClient
from iachat import app as module
from iachat.store import ConversationStore


def test_http_account_isolation_and_admin_permissions(tmp_path, monkeypatch):
    db = ConversationStore(str(tmp_path / "http-users.db"))
    db.create_user("admin", "test-admin-pass-123", admin=True)
    db.create_user("prueba", "test-user-pass-123")
    db.put("admin-conversation", [{"role": "user", "content": "private"}], owner="admin")
    db.save_memory("admin-memory", "Faro Azul", owner="admin")
    monkeypatch.setattr(module, "store", db)
    monkeypatch.setenv("IACHAT_AUTH_SECRET", "test-only-secret-for-http-regression")
    admin = TestClient(module.app)
    other = TestClient(module.app)
    guest = TestClient(module.app)

    assert guest.get("/api/conversations").status_code == 401
    assert guest.get("/api/users").status_code == 401

    assert admin.post("/auth/login", json={
        "username": "admin", "password": "test-admin-pass-123"
    }).status_code == 200
    assert other.post("/auth/login", json={
        "username": "prueba", "password": "test-user-pass-123"
    }).status_code == 200

    assert admin.get("/api/conversations/admin-conversation").status_code == 200
    assert admin.get("/api/memories").json()["memories"][0]["content"] == "Faro Azul"

    assert other.get("/api/conversations").json()["conversations"] == []
    assert other.get("/api/memories").json()["memories"] == []
    assert other.get("/api/conversations/admin-conversation").status_code == 404
    assert other.delete("/api/conversations/admin-conversation").status_code == 404
    assert other.put("/api/memories/admin-memory", json={"content": "overwritten"}).status_code == 404
    assert other.delete("/api/memories/admin-memory").status_code == 404
    assert other.post("/api/memories/suggest", json={"conversation_id": "admin-conversation"}).status_code == 404

    assert other.get("/api/users").status_code == 403
    assert other.post("/api/users", json={
        "username": "intruso", "password": "different-password"
    }).status_code == 403
    assert other.put("/api/users/admin/enabled?enabled=false").status_code == 403

    assert admin.get("/api/conversations/admin-conversation").status_code == 200
    assert admin.get("/api/memories").json()["memories"][0]["content"] == "Faro Azul"
    assert admin.post("/api/users", json={
        "username": "tercero", "password": "another-password-123"
    }).status_code == 201
    assert other.get("/api/conversations/admin-conversation").status_code == 404
