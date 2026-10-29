"""Offline contract for the public-web release smoke; no network calls."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location(
    "smoke_web_public", Path(__file__).resolve().parents[1] / "scripts" / "smoke_web_public.py"
)
smoke = module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_public_web_smoke_covers_domains_and_reads_a_page():
    seen = []

    def search(query, *, timeout, news_fallback):
        seen.append((query, timeout, news_fallback))
        return [{"url": "https://example.org/article", "title": "Sample"}]

    def read(urls, *, max_pages, max_attempts, timeout):
        assert urls == ["https://example.org/article"]
        assert (max_pages, max_attempts, timeout) == (1, 2, 3.0)
        return (object(),)

    outcomes = smoke.probe_public_web(search=search, read=read)
    assert [x["domain"] for x in outcomes] == ["instituciones", "software", "economia"]
    assert all(x["rss_results"] == 1 and x["pages_read"] == 1 for x in outcomes)
    assert all(0 < timeout <= 10 and fallback for _, timeout, fallback in seen)
    assert smoke.release_evidence_ok(outcomes)


def test_public_web_smoke_fails_closed_on_missing_domain_or_unreadable_pages():
    def search(query, *, timeout, news_fallback):
        return [] if "Python" in query else [{"url": "https://example.org/article"}]

    def read(urls, **kwargs):
        return (object(),)

    outcomes = smoke.probe_public_web(search=search, read=read)
    assert not smoke.release_evidence_ok(outcomes)

    outcomes = smoke.probe_public_web(
        search=lambda query, **kwargs: [{"url": "https://example.org/article"}],
        read=lambda urls, **kwargs: (),
    )
    assert not smoke.release_evidence_ok(outcomes)
