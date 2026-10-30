"""Real public-web release smoke: no model, credentials, billing or user data.

Checks that public RSS search and at least one HTTPS page reader actually work
on a GitHub runner. Results are external, UNVERIFIED evidence, not facts.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from iachat.web_page_reader import read_page, read_pages, PageReadError
from iachat.web_fetch import PageFetchError
from iachat.web_search import search_web

QUERIES = (
    ("instituciones", "ANSES requisitos tramites Argentina"),
    ("software", "Python documentation release notes"),
    ("economia", "precios combustibles Argentina"),
)


def probe_public_web(*, search=search_web, read=read_pages, queries=QUERIES):
    """Return evidence availability, never content or provider credentials."""
    outcomes = []
    for domain, query in queries:
        results = search(query, timeout=6.0, news_fallback=True)
        urls = [item["url"] for item in results if isinstance(item, dict) and isinstance(item.get("url"), str)]
        pages = read(urls, max_pages=1, max_attempts=3, timeout=3.0) if urls else ()
        hosts = {urlsplit(url).hostname for url in urls}
        if not pages:
            # Safe public-source diagnosis: only hostname and fixed reason codes.
            for url in urls[:4]:
                host = urlsplit(url).hostname or ""
                try:
                    read_page(url, timeout=3.0)
                except PageFetchError as exc:
                    message = str(exc)
                    if "non-200 status" in message:
                        reason = message.rsplit("HTTP_", 1)[-1].rstrip(")") if "HTTP_" in message else "non_200"
                        reason = "http_" + reason if reason.isdigit() else "non_200"
                    elif "byte limit" in message:
                        reason = "oversized"
                    elif "compressed" in message:
                        reason = "compressed"
                    elif "content type" in message:
                        reason = "media"
                    elif "request failed" in message:
                        reason = "transport"
                    else:
                        reason = "dns_or_safety"
                except (PageReadError, ValueError):
                    reason = "no_text_or_charset"
                else:
                    reason = "readable_on_retry"
                print("PUBLIC_PAGE_DIAG:", "domain=" + domain,
                      "host=" + host, "reason=" + reason, flush=True)
        outcome = {
            "domain": domain,
            "rss_results": len(urls),
            "distinct_hosts": len(hosts),
            "pages_read": len(pages),
        }
        outcomes.append(outcome)
        print(
            f"PUBLIC_WEB_UNVERIFIED domain={domain} rss={outcome['rss_results']} "
            f"hosts={outcome['distinct_hosts']} pages={outcome['pages_read']}",
            flush=True,
        )
    return outcomes


def release_evidence_ok(outcomes):
    """Require all three independent topics and at least one actually read page."""
    return (
        len(outcomes) == len(QUERIES)
        and all(item["rss_results"] > 0 for item in outcomes)
        and any(item["pages_read"] > 0 for item in outcomes)
    )


if __name__ == "__main__":
    evidence = probe_public_web()
    if not release_evidence_ok(evidence):
        raise SystemExit("FAIL: public RSS/page evidence unavailable; live web release gate blocked")
    print("PASS: public RSS across three domains and an HTTPS page read (facts NOT verified)")
