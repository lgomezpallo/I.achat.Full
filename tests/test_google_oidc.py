"""OIDC security and cross-device isolation tests; no real Google credentials."""
import json
import time
from urllib.parse import parse_qs, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from iachat import app as module
from iachat import google_auth
from iachat.store import ConversationStore


def setup_oidc(tmp_path, monkeypatch):
    db = ConversationStore(str(tmp_path / "google-test.sqlite3"))
    monkeypatch.setattr(module, "store", db)
    monkeypatch.setenv("IACHAT_GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("IACHAT_GOOGLE_CLIENT_SECRET", "test-secret-only")
    monkeypatch.setenv("IACHAT_PUBLIC_ORIGIN", "https://testserver")
    monkeypatch.setenv("IACHAT_AUTH_SECRET", "test-session-secret")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    jwk["kid"] = "test-rsa-key"
    current = {"nonce": None, "sub": "google-subject-A", "aud": "client-id.apps.googleusercontent.com"}

    class FakeResponse:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self.data

    def token_request(url, data, timeout):
        assert url == google_auth.TOKEN_URL
        assert data["grant_type"] == "authorization_code"
        assert data["code_verifier"]
        claims = {
            "iss": "https://accounts.google.com", "aud": current["aud"],
            "sub": current["sub"], "iat": int(time.time()),
            "exp": int(time.time()) + 300, "nonce": current["nonce"],
        }
        token = jwt.encode(claims, private, algorithm="RS256", headers={"kid": "test-rsa-key"})
        return FakeResponse({"id_token": token})

    def keys_request(url, timeout):
        assert url == google_auth.KEYS_URL
        return FakeResponse({"keys": [jwk]})

    monkeypatch.setattr(google_auth.httpx, "post", token_request)
    monkeypatch.setattr(google_auth.httpx, "get", keys_request)
    return db, current


def google_login(client, current):
    start = client.get("/auth/google/start", follow_redirects=False)
    assert start.status_code == 302
    assert urlsplit(start.headers["location"]).hostname == "accounts.google.com"
    params = parse_qs(urlsplit(start.headers["location"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["https://testserver/auth/google/callback"]
    flow = google_auth.GoogleOIDC.read_flow(
        client.cookies.get("iachat_google_flow"), "test-session-secret"
    )
    assert params["state"] == [flow["state"]]
    assert params["nonce"] == [flow["nonce"]]
    current["nonce"] = flow["nonce"]
    callback = client.get("/auth/google/callback", params={"code": "test-code", "state": flow["state"]}, follow_redirects=False)
    return callback


def test_google_login_same_sub_syncs_and_other_sub_isolated(tmp_path, monkeypatch):
    db, current = setup_oidc(tmp_path, monkeypatch)
    a = TestClient(module.app, base_url="https://testserver")
    b = TestClient(module.app, base_url="https://testserver")
    other = TestClient(module.app, base_url="https://testserver")
    assert a.get("/auth/status").json()["google_enabled"] is True
    assert google_login(a, current).status_code == 303
    user = a.get("/auth/status").json()["username"]
    assert user.startswith("g_")
    db.put("private-conversation", [{"role": "user", "content": "private"}], owner=user)
    assert google_login(b, current).status_code == 303
    assert b.get("/auth/status").json()["username"] == user
    assert b.get("/api/conversations/private-conversation").status_code == 200
    current["sub"] = "google-subject-B"
    assert google_login(other, current).status_code == 303
    assert other.get("/auth/status").json()["username"] != user
    assert other.get("/api/conversations/private-conversation").status_code == 404
    assert len(db.list_users()) == 2


def test_google_rejects_wrong_state_nonce_and_audience(tmp_path, monkeypatch):
    _, current = setup_oidc(tmp_path, monkeypatch)
    c = TestClient(module.app, base_url="https://testserver")
    start = c.get("/auth/google/start", follow_redirects=False)
    flow = google_auth.GoogleOIDC.read_flow(c.cookies.get("iachat_google_flow"), "test-session-secret")
    current["nonce"] = flow["nonce"]
    assert c.get("/auth/google/callback", params={"code": "x", "state": "wrong"}).status_code == 401
    assert c.get("/auth/status").json()["authenticated"] is False
    current["nonce"] = "wrong-nonce"
    assert c.get("/auth/google/callback", params={"code": "x", "state": flow["state"]}).status_code == 401
    current["nonce"] = flow["nonce"]
    current["aud"] = "attacker-client"
    assert c.get("/auth/google/callback", params={"code": "x", "state": flow["state"]}).status_code == 401
    assert c.get("/auth/status").json()["authenticated"] is False


def test_google_requires_configuration_and_does_not_link_legacy_accounts(tmp_path, monkeypatch):
    db, current = setup_oidc(tmp_path, monkeypatch)
    db.create_user("admin", "test-legacy-password", admin=True)
    client = TestClient(module.app, base_url="https://testserver")
    assert google_login(client, current).status_code == 303
    assert client.get("/auth/status").json()["username"] != "admin"
    assert db.get_user("admin")["admin"] is True
    monkeypatch.delenv("IACHAT_GOOGLE_CLIENT_SECRET")
    assert client.get("/auth/google/start").status_code == 503
    assert client.get("/auth/status").json()["google_enabled"] is False
