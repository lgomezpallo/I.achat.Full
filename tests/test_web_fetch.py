"""Offline security and behavior tests for the page fetcher (no network)."""
from __future__ import annotations

import socket

import pytest

from iachat import web_fetch as wf


class FakeResponse:
    def __init__(self, *, status=200, body=b"<p>Hello</p>", headers=None):
        self.status = status
        self.body = body
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, amount):
        return self.body[:amount]


class FakeConnection:
    response = FakeResponse()
    instances = []

    def __init__(self, host, ip, timeout):
        self.host, self.ip, self.timeout = host, ip, timeout
        self.requests = []
        self.closed = False
        self.instances.append(self)

    def request(self, method, target, headers):
        self.requests.append((method, target, headers))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def fake_network(monkeypatch):
    FakeConnection.instances = []
    FakeConnection.response = FakeResponse()
    monkeypatch.setattr(wf, "_PinnedHTTPSConnection", FakeConnection)
    monkeypatch.setattr(
        wf.socket, "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )


@pytest.mark.parametrize("url", [
    "http://example.com/", "https://localhost/", "https://localhost.local/",
    "https://metadata.google.internal/", "https://example.test/",
    "https://127.0.0.1/", "https://[::1]/", "https://2130706433/",
    "https://127.1/", "https://example.com:444/", "https://user@example.com/",
    "https://example.com\\@evil.com/", "https://example.com/\nX-Test:1",
    "https://example.com./", "https://example_com/", "https://a/",
    " https://example.com/", "https://example.com/\x00",
])
def test_rejects_unsafe_urls_without_network(url):
    with pytest.raises(wf.PageFetchError):
        wf.fetch_page(url)
    assert not FakeConnection.instances


@pytest.mark.parametrize("answers", [
    ["127.0.0.1"], ["169.254.169.254"], ["10.0.0.1"],
    ["192.168.1.2"], ["::1"], ["fc00::1"],
    ["93.184.216.34", "10.0.0.2"], [],
])
def test_rejects_nonpublic_or_mixed_dns(monkeypatch, answers):
    monkeypatch.setattr(
        wf.socket, "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
            for address in answers
        ],
    )
    with pytest.raises(wf.PageFetchError):
        wf.fetch_page("https://example.com/news")
    assert not FakeConnection.instances


def test_fetches_only_one_https_request_to_pinned_public_ip():
    result = wf.fetch_page("https://example.com/news?q=hello")
    assert result.payload == b"<p>Hello</p>"
    assert result.content_type.startswith("text/html")
    assert len(FakeConnection.instances) == 1
    conn = FakeConnection.instances[0]
    assert (conn.host, conn.ip) == ("example.com", "93.184.216.34")
    method, target, headers = conn.requests[0]
    assert method == "GET"
    assert target == "/news?q=hello"
    assert headers["Accept-Encoding"] == "identity"
    assert conn.closed


def test_redirect_is_not_followed():
    FakeConnection.response = FakeResponse(
        status=302, headers={"Location": "https://127.0.0.1/admin"}
    )
    with pytest.raises(wf.PageFetchError, match="non-200"):
        wf.fetch_page("https://example.com/")
    assert len(FakeConnection.instances) == 1
    assert FakeConnection.instances[0].closed


@pytest.mark.parametrize("headers", [
    {"Content-Type": "application/pdf"},
    {"Content-Type": "image/png"},
    {"Content-Type": "text/html", "Content-Encoding": "gzip"},
    {"Content-Type": "text/html", "Content-Length": "999999"},
    {"Content-Type": "text/html", "Content-Length": "invalid"},
])
def test_rejects_unsupported_or_oversized_headers(headers):
    FakeConnection.response = FakeResponse(headers=headers)
    with pytest.raises(wf.PageFetchError):
        wf.fetch_page("https://example.com/")


def test_rejects_stream_exceeding_limit_even_without_content_length():
    FakeConnection.response = FakeResponse(body=b"x" * 501)
    with pytest.raises(wf.PageFetchError, match="byte limit"):
        wf.fetch_page("https://example.com/", max_bytes=500)


@pytest.mark.parametrize("kwargs", [
    {"max_bytes": 0}, {"max_bytes": wf.MAX_PAGE_BYTES + 1},
    {"timeout": float("nan")}, {"timeout": float("inf")},
    {"timeout": "bad"},
])
def test_invalid_limits_do_not_connect(kwargs):
    with pytest.raises(wf.PageFetchError):
        wf.fetch_page("https://example.com/", **kwargs)
    assert not FakeConnection.instances


def test_timeout_is_bounded():
    wf.fetch_page("https://example.com/", timeout=100)
    assert FakeConnection.instances[0].timeout == 10.0


def test_tls_connect_uses_pinned_ip_and_original_hostname(monkeypatch):
    # Test the real connection class, not the FakeConnection fixture.
    class FakeSocket:
        closed = False
        def close(self):
            self.closed = True

    class FakeTLSContext:
        def wrap_socket(self, raw, server_hostname):
            assert server_hostname == "example.com"
            return raw

    raw = FakeSocket()
    seen = []
    monkeypatch.setattr(
        wf.socket, "create_connection",
        lambda address, timeout: (seen.append((address, timeout)), raw)[1],
    )
    conn = wf._PinnedHTTPSConnection.__mro__[1] if False else None
    # Retrieve original class by reloading module; only connect is exercised.
    import importlib
    original = importlib.reload(wf)._PinnedHTTPSConnection
    connection = original("example.com", "93.184.216.34", 2.0)
    connection._context = FakeTLSContext()
    connection.connect()
    assert seen == [(("93.184.216.34", 443), 2.0)]
    assert connection.sock is raw
    connection.close()
