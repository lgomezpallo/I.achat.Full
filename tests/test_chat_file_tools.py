"""The regular chat endpoint can create/edit real private downloadable files."""
import json

from fastapi.testclient import TestClient

import iachat.app as app_module
from iachat.file_workspace import FileWorkspace
from iachat.store import ConversationStore
from iachat.tool_planner import FileAction, select_file_action


class FakeBackend:
    def __init__(self):
        self.file_id = None

    def answer(self, messages, images=None):
        policy = messages[0]["content"] if messages[0]["role"] == "system" else ""
        request = messages[-1]["content"]
        if "selector de herramientas" in policy:
            task = json.loads(request)["request"]
            if task.startswith("Creá"):
                return '{"action":"create"}'
            if task.startswith("Actualizá"):
                return json.dumps({"action": "edit", "file_id": self.file_id})
            return '{"action":"answer"}'
        if "generador y editor" in policy:
            if self.file_id and "DOCUMENTO EXISTENTE" in request:
                return json.dumps({"name": "malicious-change.pdf", "content": "# Informe\n\nVersión corregida"})
            return json.dumps({"name": "informe.pdf", "content": "# Informe\n\nContenido de prueba"})
        return "Una respuesta normal."


def test_selector_rejects_unknown_file_ids_and_ambiguous_output():
    class Backend:
        def __init__(self, output):
            self.output = output
        def answer(self, messages):
            return self.output
    files = [{"id": "owned", "name": "informe.pdf"}]
    assert select_file_action("Editá el archivo", files, Backend('{"action":"edit","file_id":"foreign"}')) == FileAction()
    assert select_file_action("Editá el archivo", files, Backend('{"action":"edit","file_id":"owned"}')) == FileAction("edit", "owned")
    assert select_file_action("Hola", files, Backend('{"action":"create","extra":true}')) == FileAction()
    assert select_file_action("Hola", files, Backend("texto inesperado")) == FileAction()
    assert select_file_action("Hola", files, Backend("ERROR")) == FileAction()


def test_authenticated_chat_creates_edits_and_downloads_pdf(monkeypatch, tmp_path):
    db = str(tmp_path / "chat-tools.sqlite")
    monkeypatch.setattr(app_module, "store", ConversationStore(db))
    monkeypatch.setattr(app_module, "file_workspace", FileWorkspace(db))
    monkeypatch.setenv("IACHAT_AUTH_SECRET", "only-for-isolated-tests")
    assert app_module.store.create_user("alice", "password123", admin=True)
    assert app_module.store.create_user("bob", "password123")
    backend = FakeBackend()
    monkeypatch.setattr(app_module, "get_backend", lambda: backend)
    monkeypatch.setattr("iachat.auto_memory.learn", lambda *args: None)
    with TestClient(app_module.app, base_url="https://testserver") as client:
        assert client.post("/auth/login", json={"username": "alice", "password": "password123"}).status_code == 200
        created = client.post("/api/chat", json={"text": "Creá un informe PDF descargable sobre una prueba."})
        assert created.status_code == 200, created.text
        payload = created.json()
        file_id = payload["generated_file"]["id"]
        backend.file_id = file_id
        assert payload["generated_file"]["name"] == "informe.pdf"
        assert f"/api/files/{file_id}/download" in payload["answer"]
        pdf = client.get(f"/api/files/{file_id}/download")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
        edited = client.post("/api/chat", json={
            "conversation_id": payload["conversation_id"],
            "text": "Actualizá el informe que acabás de crear.",
        })
        assert edited.status_code == 200, edited.text
        assert edited.json()["generated_file"]["id"] == file_id
        assert "actualizado" in edited.json()["answer"].lower()
        assert "Versión corregida" in app_module.file_workspace.get("alice", file_id)["content"]
        history = client.get("/api/conversations/" + payload["conversation_id"])
        assert history.status_code == 200
        assert f"/api/files/{file_id}/download" in history.json()["history"][-1]["content"]
        normal = client.post("/api/chat", json={"text": "¿Qué es un PDF?"})
        assert normal.status_code == 200 and normal.json()["generated_file"] is None
        assert normal.json()["answer"] == "Una respuesta normal."
        client.post("/auth/logout")
        client.post("/auth/login", json={"username": "bob", "password": "password123"})
        assert client.get(f"/api/files/{file_id}/download").status_code == 404
