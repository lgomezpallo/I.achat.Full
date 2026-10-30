import json
import pytest
from fastapi.testclient import TestClient

import iachat.app as app_module
from iachat.file_workspace import FileWorkspace, WorkspaceError, parse_generated_file
from iachat.store import ConversationStore


def test_workspace_owner_isolation_and_update(tmp_path):
    files = FileWorkspace(str(tmp_path / "files.db"))
    saved = files.save("alice", "reporte.csv", "obra,estado\n123,pendiente")
    assert files.get("alice", saved["id"])["content"].startswith("obra,")
    assert files.get("bob", saved["id"]) is None
    with pytest.raises(WorkspaceError, match="file_not_found"):
        files.save("bob", "otro.csv", "robado", saved["id"])
    assert files.save("alice", "reporte.csv", "obra,estado\n123,terminada", saved["id"])["id"] == saved["id"]
    assert files.list("bob") == []
    assert not files.delete("bob", saved["id"])
    assert files.delete("alice", saved["id"])


@pytest.mark.parametrize("name", ["../secreto.txt", ".env", "a.pdf", "x.txt/../y.txt", "bad\nname.md", "x.js"])
def test_reject_unsafe_names(tmp_path, name):
    files = FileWorkspace(str(tmp_path / "files.db"))
    with pytest.raises(WorkspaceError, match="invalid_filename"):
        files.save("alice", name, "test")


def test_file_size_and_model_response_limits(tmp_path):
    files = FileWorkspace(str(tmp_path / "files.db"))
    with pytest.raises(WorkspaceError, match="file_too_large"):
        files.save("alice", "x.txt", "a" * 200001)
    assert parse_generated_file('```json\n{"name":"a.md","content":"hola"}\n```') == ("a.md", "hola")
    with pytest.raises(WorkspaceError, match="invalid_file_response"):
        parse_generated_file("Te hice un archivo")
    with pytest.raises(WorkspaceError, match="invalid_filename"):
        parse_generated_file('{"name":"../bad.md","content":"hola"}')


def test_authenticated_file_generation_download_and_edit(monkeypatch, tmp_path):
    db = str(tmp_path / "isolated.db")
    monkeypatch.setattr(app_module, "store", ConversationStore(db))
    monkeypatch.setattr(app_module, "file_workspace", FileWorkspace(db))
    monkeypatch.setenv("IACHAT_AUTH_SECRET", "test-secret-not-production")
    assert app_module.store.create_user("alice", "password123", admin=True)
    assert app_module.store.create_user("bob", "password123")
    class FakeBackend:
        def answer(self, messages):
            if "Editar" in messages[-1]["content"]:
                return json.dumps({"name": "wrong-name.md", "content": "# Modificado"})
            return json.dumps({"name": "informe.md", "content": "# Informe\nTexto real"})
    monkeypatch.setattr(app_module, "get_backend", lambda: FakeBackend())
    with TestClient(app_module.app, base_url="https://testserver") as client:
        assert client.get("/api/files").status_code == 401
        assert client.post("/auth/login", json={"username":"alice","password":"password123"}).status_code == 200
        created = client.post("/api/files/generate", json={"instruction":"Generá un informe breve"})
        assert created.status_code == 201, created.text
        file_id = created.json()["id"]
        download = client.get("/api/files/" + file_id + "/download")
        assert download.status_code == 200
        assert download.content == b"# Informe\nTexto real"
        assert "attachment;" in download.headers["content-disposition"]
        assert download.headers["x-content-type-options"] == "nosniff"
        assert client.get("/api/files/" + file_id).json()["name"] == "informe.md"
        edited = client.post("/api/files/generate", json={"instruction":"Editar el informe", "file_id":file_id})
        assert edited.status_code == 201, edited.text
        assert edited.json()["name"] == "informe.md"
        assert client.get("/api/files/" + file_id).json()["content"] == "# Modificado"
        client.post("/auth/logout")
        client.post("/auth/login", json={"username":"bob","password":"password123"})
        assert client.get("/api/files/" + file_id + "/download").status_code == 404
        assert client.put("/api/files/" + file_id, json={"name":"other.md","content":"x"}).status_code == 404
        assert client.delete("/api/files/" + file_id).status_code == 404
        assert client.post("/api/files/generate", json={"instruction":"Editar", "file_id":file_id}).status_code == 404
