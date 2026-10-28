"""Offline RSS provider tests: every HTTP request is handled by MockTransport."""
import httpx

from iachat import web_search


def rss(*items):
    body = "".join(
        f"<item><title>{title}</title><link>{url}</link>"
        f"<description>{description}</description></item>"
        for title, url, description in items
    )
    return f"<?xml version='1.0'?><rss><channel>{body}</channel></rss>".encode()


def install_http(monkeypatch, handler):
    original_client = httpx.Client

    def mock_client(*args, **kwargs):
        assert kwargs["follow_redirects"] is False
        return original_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(web_search.httpx, "Client", mock_client)


def test_bing_general_search_no_news_request(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url)
        assert request.url.host == "www.bing.com"
        return httpx.Response(200, content=rss(
            ("Documentación", "https://fastapi.tiangolo.com/tutorial/", "&lt;b&gt;Guía&lt;/b&gt; &amp; tutorial")
        ))

    install_http(monkeypatch, handler)
    result = web_search.search_web("Buscá documentación FastAPI")
    assert len(calls) == 1
    assert result == [{
        "title": "Documentación",
        "url": "https://fastapi.tiangolo.com/tutorial/",
        "snippet": "Guía & tutorial",
    }]


def test_news_fallback_after_bing_failure(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "www.bing.com":
            return httpx.Response(503)
        assert request.url.host == "news.google.com"
        return httpx.Response(200, content=rss(
            ("Partido", "https://news.google.com/rss/articles/123", "Horario por confirmar")
        ))

    install_http(monkeypatch, handler)
    results = web_search.search_web("¿Cuándo juega River?")
    assert calls == ["www.bing.com", "news.google.com"]
    assert results[0]["title"] == "Partido"


def test_timeless_query_does_not_use_news_only_fallback(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(503)

    install_http(monkeypatch, handler)
    assert web_search.search_web("Manual de FastAPI") == []
    assert calls == ["www.bing.com"]


def test_feed_filters_unsafe_links_and_duplicates(monkeypatch):
    def handler(request):
        return httpx.Response(200, content=rss(
            ("HTTP", "http://example.com/x", "no"),
            ("Private", "https://10.0.0.1/x", "no"),
            ("Short IP", "https://127.1/x", "no"),
            ("Credentials", "https://user:pass@example.com/x", "no"),
            ("Local", "https://machine.local/x", "no"),
            ("Other port", "https://example.com:8080/x", "no"),
            ("Valid", "https://example.com/a", "yes"),
            ("Duplicate", "https://example.com/a", "same"),
        ))

    install_http(monkeypatch, handler)
    assert web_search.search_web("documentación") == [{
        "title": "Valid", "url": "https://example.com/a", "snippet": "yes"
    }]


def test_oversized_stream_is_rejected(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(200, content=b"x" * (web_search.MAX_RESPONSE_BYTES + 1))

    install_http(monkeypatch, handler)
    assert web_search.search_web("documentación") == []
    assert calls == ["www.bing.com"]


def test_oversized_content_length_is_rejected(monkeypatch):
    def handler(request):
        return httpx.Response(200, headers={"content-length": "400001"}, content=b"x")

    install_http(monkeypatch, handler)
    assert web_search.search_web("documentación") == []


def test_redirects_not_followed_and_news_fallback_used(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "www.bing.com":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        return httpx.Response(200, content=rss(
            ("News", "https://news.google.com/rss/articles/123", "Info")
        ))

    install_http(monkeypatch, handler)
    assert len(web_search.search_web("Noticias de IA hoy")) == 1
    assert calls == ["www.bing.com", "news.google.com"]


def test_blank_query_never_uses_network(monkeypatch):
    def handler(request):
        raise AssertionError("no request expected")

    install_http(monkeypatch, handler)
    assert web_search.search_web("   ") == []


def test_feed_is_bounded_to_five_results(monkeypatch):
    items = [(str(i), f"https://example.com/{i}", "snippet") for i in range(12)]

    def handler(request):
        return httpx.Response(200, content=rss(*items))

    install_http(monkeypatch, handler)
    assert len(web_search.search_web("documentación")) == 5


def test_bad_xml_uses_news_fallback(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "www.bing.com":
            return httpx.Response(200, content=b"<rss><broken>")
        return httpx.Response(200, content=rss(
            ("Result", "https://example.com/valid", "OK")
        ))

    install_http(monkeypatch, handler)
    assert len(web_search.search_web("últimas noticias")) == 1
    assert calls == ["www.bing.com", "news.google.com"]


def test_snippets_are_not_described_as_verified_pages(monkeypatch):
    monkeypatch.setattr(web_search, "search_web", lambda query: [
        {"title": "X", "url": "https://example.com/x", "snippet": "Dato"}
    ])
    evidence = web_search.web_evidence("hoy")
    assert "no páginas leídas ni hechos verificados" in evidence
    assert "https://example.com/x" in evidence


def test_rss_pubdate_is_normalized_to_utc_without_changing_event_date(monkeypatch):
    feed = rss(("Evento", "https://example.com/evento", "El evento será mañana"))
    feed = feed.replace(
        b"</item>",
        b"<pubDate>Tue, 27 Oct 2026 23:30:00 -0300</pubDate></item>",
    )
    install_http(monkeypatch, lambda request: httpx.Response(200, content=feed))
    results = web_search.search_web("evento")
    assert results == [{
        "title": "Evento",
        "url": "https://example.com/evento",
        "snippet": "El evento será mañana",
        "published_at_utc": "2026-10-28T02:30:00+00:00",
    }]


def test_rss_pubdate_missing_invalid_or_without_timezone_is_omitted(monkeypatch):
    feed = (
        b"<rss><channel>"
        b"<item><title>Sin fecha</title><link>https://example.com/a</link></item>"
        b"<item><title>Sin zona</title><link>https://example.com/b</link>"
        b"<pubDate>Tue, 27 Oct 2026 23:30:00</pubDate></item>"
        b"<item><title>Malformada</title><link>https://example.com/c</link>"
        b"<pubDate>no es fecha</pubDate></item>"
        b"</channel></rss>"
    )
    install_http(monkeypatch, lambda request: httpx.Response(200, content=feed))
    results = web_search.search_web("documentación")
    assert len(results) == 3
    assert all("published_at_utc" not in item for item in results)
