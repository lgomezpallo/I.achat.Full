"""Bounded composition of HTTPS fetching and offline text extraction.

Page content is external, untrusted data. Reading a page does NOT verify that
its claims are true and must never be treated as instructions for IAchat.
This module is intentionally not connected to the chat handler yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from typing import Iterable

from .web_content import MAX_TEXT_CHARS, extract_page_text
from .web_fetch import PageFetchError, fetch_page

MAX_PAGES = 2
MAX_ATTEMPTS = 4
MAX_CANDIDATES = 10


class PageReadError(ValueError):
    """A fetched page did not contain usable text."""


@dataclass(frozen=True)
class ReadPage:
    url: str
    text: str
    evidence_kind: str = "external_page_unverified"


def read_page(
    url: str, *, timeout: float = 5.0, max_chars: int = MAX_TEXT_CHARS
) -> ReadPage:
    """Read one public HTTPS page using the pinned-IP, SSRF-safe fetcher."""
    if type(max_chars) is not int or not 1 <= max_chars <= MAX_TEXT_CHARS:
        raise ValueError("invalid text limit")
    fetched = fetch_page(url, timeout=timeout)
    text = extract_page_text(
        fetched.payload, fetched.content_type, max_chars=max_chars
    )
    if not text:
        raise PageReadError("page has no readable content")
    return ReadPage(url=fetched.url, text=text)


def read_pages(
    urls: Iterable[str],
    *,
    max_pages: int = MAX_PAGES,
    max_attempts: int = MAX_ATTEMPTS,
    timeout: float = 5.0,
) -> tuple[ReadPage, ...]:
    """Read at most two distinct pages, trying at most four candidate URLs.

    Individual fetch/parse failures are skipped. No URL is retried, no
    redirect is followed, and a failed page does not count as evidence.
    """
    if (
        type(max_pages) is not int
        or type(max_attempts) is not int
        or not 1 <= max_pages <= MAX_PAGES
        or not max_pages <= max_attempts <= MAX_ATTEMPTS
    ):
        raise ValueError("invalid page read budget")
    seen: set[str] = set()
    found: list[ReadPage] = []
    attempts = 0
    # Duplicates and malformed entries must not make an infinite iterable hang.
    for url in islice(urls, MAX_CANDIDATES):
        if attempts >= max_attempts or len(found) >= max_pages:
            break
        if not isinstance(url, str) or url in seen:
            continue
        seen.add(url)
        attempts += 1
        try:
            found.append(read_page(url, timeout=timeout))
        except (PageFetchError, PageReadError, ValueError):
            continue
    return tuple(found)
