"""Single-request HTTPS page fetcher with DNS pinning and strict SSRF guards.

This module is intentionally NOT wired to IAchat yet. Its output is untrusted
page bytes, intended for the separately reviewed web_content extractor.
It does not use a proxy, follow redirects, or make paid API calls.
"""
from __future__ import annotations

import http.client
import ipaddress
import math
import re
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

MAX_PAGE_BYTES = 400_000
MAX_URL_CHARS = 2_048
_ALLOWED_TYPES = frozenset({"text/html", "text/plain", "application/xhtml+xml"})
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class PageFetchError(ValueError):
    """Page was rejected or could not be fetched safely."""


@dataclass(frozen=True)
class FetchedPage:
    url: str
    content_type: str
    payload: bytes


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Verify TLS for the hostname while connecting only to the checked IP."""

    def __init__(self, hostname: str, ip: str, timeout: float) -> None:
        super().__init__(
            hostname, port=443, timeout=timeout, context=ssl.create_default_context()
        )
        self._pinned_ip = ip

    def connect(self) -> None:
        # Do not resolve the hostname again: a second lookup enables DNS rebinding.
        raw = socket.create_connection((self._pinned_ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _validated_target(url: str) -> tuple[str, str]:
    if (
        not isinstance(url, str)
        or not 1 <= len(url) <= MAX_URL_CHARS
        or any(ord(ch) < 33 or ord(ch) == 127 or ch == "\\" for ch in url)
    ):
        raise PageFetchError("invalid page URL")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
            or host.endswith(".")
        ):
            raise PageFetchError("only public HTTPS pages are allowed")
        host = host.encode("idna").decode("ascii").lower()
        labels = host.split(".")
        if (
            len(host) > 253
            or len(labels) < 2
            or any(not _HOST_LABEL.fullmatch(label) for label in labels)
            or len(labels[-1]) < 2
            or labels[-1].isdigit()
            or host.endswith((".local", ".localhost", ".internal", ".test", ".invalid", ".onion"))
        ):
            raise PageFetchError("invalid public hostname")
        # IP literals, including ambiguous numeric encodings, are never accepted.
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if re.fullmatch(r"[0-9.]+", host):
                raise PageFetchError("numeric hostnames are forbidden")
        else:
            raise PageFetchError("IP literals are forbidden")
        path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
        query = quote(parsed.query, safe="/?%:@!$&'()*+,;=-._~")
        return host, path + ("?" + query if parsed.query else "")
    except (ValueError, UnicodeError) as exc:
        raise PageFetchError("invalid page URL") from exc


def _resolve_public_ip(host: str) -> str:
    # All DNS answers must be global. The selected address is pinned for TLS.
    try:
        answers = socket.getaddrinfo(
            host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
        addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
        if not addresses or any(
            not ipaddress.ip_address(address).is_global for address in addresses
        ):
            raise PageFetchError("DNS resolved to a non-public address")
        return addresses[0]
    except (OSError, ValueError, IndexError) as exc:
        raise PageFetchError("public DNS validation failed") from exc


def fetch_page(
    url: str, *, timeout: float = 5.0, max_bytes: int = MAX_PAGE_BYTES
) -> FetchedPage:
    """Fetch one public HTTPS page with a strict byte limit and no redirects.

    Hostname is resolved and every answer checked before connecting to the
    selected literal IP; TLS SNI and certificate verification use the hostname.
    The caller must treat the returned payload as untrusted external content.
    """
    host, target = _validated_target(url)
    if not isinstance(max_bytes, int) or not 1 <= max_bytes <= MAX_PAGE_BYTES:
        raise PageFetchError("invalid page size limit")
    try:
        timeout = float(timeout)
        if not math.isfinite(timeout):
            raise ValueError("non-finite timeout")
    except (TypeError, ValueError, OverflowError) as exc:
        raise PageFetchError("invalid page timeout") from exc
    timeout = min(max(timeout, 0.5), 10.0)
    ip = _resolve_public_ip(host)
    connection = _PinnedHTTPSConnection(host, ip, timeout)
    try:
        connection.request(
            "GET", target,
            headers={
                "Host": host,
                "User-Agent": "IAchat/1.0 (bounded public page reader)",
                "Accept": "text/html, text/plain, application/xhtml+xml",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        # In particular, NEVER follow redirects to an unvalidated destination.
        if response.status != 200:
            raise PageFetchError("page returned a non-200 status")
        media_type = (response.getheader("Content-Type", "") or "").split(";", 1)[0].strip().lower()
        if media_type not in _ALLOWED_TYPES:
            raise PageFetchError("unsupported page content type")
        encoding = (response.getheader("Content-Encoding", "identity") or "").lower().strip()
        if encoding not in ("identity", ""):
            raise PageFetchError("compressed page content is not allowed")
        length = response.getheader("Content-Length")
        if length is not None:
            try:
                if int(length) < 0 or int(length) > max_bytes:
                    raise PageFetchError("page exceeds byte limit")
            except ValueError as exc:
                raise PageFetchError("invalid content length") from exc
        payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise PageFetchError("page exceeds byte limit")
        return FetchedPage(url=url, content_type=response.getheader("Content-Type", ""), payload=payload)
    except (OSError, http.client.HTTPException) as exc:
        raise PageFetchError("page request failed") from exc
    finally:
        connection.close()
