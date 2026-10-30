"""Google OIDC authorization-code + PKCE, with verified sub (never email identity)."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode, urlsplit
import httpx
import jwt

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
KEYS_URL = "https://www.googleapis.com/oauth2/v3/certs"

class OIDCError(Exception):
    pass

def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")

def unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

class GoogleOIDC:
    @staticmethod
    def settings():
        client = os.getenv("IACHAT_GOOGLE_CLIENT_ID", "").strip()
        secret = os.getenv("IACHAT_GOOGLE_CLIENT_SECRET", "").strip()
        origin = os.getenv("IACHAT_PUBLIC_ORIGIN", "").strip().rstrip("/")
        signing = os.getenv("IACHAT_AUTH_SECRET", "")
        parts = urlsplit(origin)
        if not client or not secret or not signing or parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.path or parts.query or parts.fragment or parts.port not in (None, 443):
            raise OIDCError("google_not_configured")
        return client, secret, origin + "/auth/google/callback", signing

    @classmethod
    def configured(cls):
        try:
            cls.settings()
            return True
        except OIDCError:
            return False

    @staticmethod
    def read_flow(cookie, signing):
        try:
            payload, sig = cookie.split(".", 1)
            expected = hmac.new(signing.encode(), payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                raise ValueError("bad_signature")
            flow = json.loads(unb64(payload))
            if int(flow["exp"]) < time.time() or not all(isinstance(flow[k], str) and len(flow[k]) >= 24 for k in ("state", "nonce", "verifier")):
                raise ValueError("expired_or_invalid")
            return flow
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise OIDCError("invalid_flow") from exc

    def begin(self):
        client, _, redirect, signing = self.settings()
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        challenge = b64(hashlib.sha256(verifier.encode()).digest())
        payload = b64(json.dumps({"state": state, "nonce": nonce, "verifier": verifier, "exp": int(time.time()) + 600}, separators=(",", ":")).encode())
        cookie = payload + "." + hmac.new(signing.encode(), payload.encode(), hashlib.sha256).hexdigest()
        url = AUTH_URL + "?" + urlencode({"client_id": client, "redirect_uri": redirect, "response_type": "code", "scope": "openid email profile", "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"})
        return url, cookie

    def complete(self, code, state, cookie):
        client, secret, redirect, signing = self.settings()
        flow = self.read_flow(cookie, signing)
        if not code or not state or not hmac.compare_digest(state, flow["state"]):
            raise OIDCError("state_mismatch")
        try:
            response = httpx.post(TOKEN_URL, data={"code": code, "client_id": client, "client_secret": secret, "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": flow["verifier"]}, timeout=12)
            response.raise_for_status()
            token = response.json().get("id_token")
            if not isinstance(token, str) or len(token) > 16384:
                raise OIDCError("missing_token")
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise OIDCError("invalid_algorithm")
            response = httpx.get(KEYS_URL, timeout=12)
            response.raise_for_status()
            key = next((k for k in response.json().get("keys", []) if k.get("kid") == header["kid"] and k.get("kty") == "RSA" and k.get("use", "sig") == "sig"), None)
            if key is None:
                raise OIDCError("unknown_key")
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
            claims = jwt.decode(token, public_key, algorithms=["RS256"], audience=client, issuer=["https://accounts.google.com", "accounts.google.com"], leeway=30, options={"require": ["sub", "iss", "aud", "exp", "iat", "nonce"]})
            if not hmac.compare_digest(str(claims["nonce"]), flow["nonce"]) or (claims.get("azp") and claims["azp"] != client):
                raise OIDCError("nonce_or_azp_mismatch")
            subject = claims["sub"]
            if not isinstance(subject, str) or not 1 <= len(subject) <= 255:
                raise OIDCError("invalid_subject")
            return subject
        except (httpx.HTTPError, ValueError, TypeError, KeyError, jwt.PyJWTError) as exc:
            raise OIDCError("verification_failed") from exc
