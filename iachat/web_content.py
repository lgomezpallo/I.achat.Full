"""Bounded, offline extraction of readable web-page text.

This module never opens URLs. A separate, SSRF-safe fetcher must validate and
retrieve remote pages before passing bytes here. External text is untrusted.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

MAX_PAGE_BYTES = 400_000
MAX_TEXT_CHARS = 8_000
_SKIP_TAGS = frozenset({
    "head", "script", "style", "noscript", "template", "svg",
    "nav", "footer", "aside", "form", "button", "dialog",
})
_BLOCK_TAGS = frozenset({
    "article", "main", "section", "div", "p", "br", "hr", "li",
    "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
    "tr", "td", "th", "pre",
})
_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
})
_ALLOWED_ENCODINGS = {
    "utf-8": "utf-8", "utf8": "utf-8",
    "iso-8859-1": "iso-8859-1", "latin1": "iso-8859-1",
    "windows-1252": "cp1252", "cp1252": "cp1252",
}


class _VisibleText(HTMLParser):
    def __init__(self, limit: int):
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.parts: list[str] = []
        self.size = 0
        self.skip_depth = 0

    def _add(self, value: str) -> None:
        remaining = self.limit - self.size
        if remaining > 0:
            value = value[:remaining]
            self.parts.append(value)
            self.size += len(value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.skip_depth:
            if tag not in _VOID_TAGS:
                self.skip_depth += 1
            return
        attributes = dict(attrs)
        hidden = (
            "hidden" in attributes
            or attributes.get("aria-hidden", "").lower() == "true"
            or bool(re.search(r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\b",
                              attributes.get("style") or "", re.I))
        )
        if tag in _SKIP_TAGS or hidden:
            if tag not in _VOID_TAGS:
                self.skip_depth = 1
            return
        if tag in _BLOCK_TAGS:
            self._add("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            if tag not in _VOID_TAGS:
                self.skip_depth -= 1
            return
        if tag in _BLOCK_TAGS:
            self._add("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self._add(data)


def extract_page_text(
    payload: bytes,
    content_type: str,
    *,
    max_bytes: int = MAX_PAGE_BYTES,
    max_chars: int = MAX_TEXT_CHARS,
) -> str:
    """Extract bounded visible text from HTML or plain text, without I/O.

    Raises ValueError for unsupported media, charset or oversized payloads.
    A caller must independently enforce streaming limits and safe URL fetching.
    """
    if not 1 <= max_bytes <= MAX_PAGE_BYTES or not 1 <= max_chars <= MAX_TEXT_CHARS:
        raise ValueError("invalid page limits")
    if len(payload) > max_bytes:
        raise ValueError("page exceeds byte limit")
    media = content_type.split(";", 1)[0].strip().lower()
    if media not in {"text/html", "text/plain", "application/xhtml+xml"}:
        raise ValueError("unsupported page content type")
    match = re.search(r"(?:^|;)\s*charset\s*=\s*['\"]?([a-zA-Z0-9._-]+)", content_type, re.I)
    charset = (match.group(1).lower() if match else "utf-8")
    encoding = _ALLOWED_ENCODINGS.get(charset)
    if encoding is None:
        raise ValueError("unsupported page charset")
    decoded = payload.decode(encoding, errors="replace")
    if media == "text/plain":
        return _normalize(decoded[:max_chars])[:max_chars]
    parser = _VisibleText(max_chars)
    parser.feed(decoded)
    parser.close()
    return _normalize("".join(parser.parts))[:max_chars]


def _normalize(text: str) -> str:
    text = re.sub(r"[\t\f\v ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
