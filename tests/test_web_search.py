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


def test_current_news_preferred_over_unrelated_bing_results(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        assert request.url.host == "news.google.com"
        return httpx.Response(200, content=rss(
            ("Partido", "https://news.google.com/rss/articles/123", "Horario por confirmar")
        ))

    install_http(monkeypatch, handler)
    results = web_search.search_web("¿Cuándo juega River?")
    assert calls == ["news.google.com"]
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


def test_news_redirect_not_followed_and_generic_fallback_used(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "news.google.com":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        return httpx.Response(200, content=rss(
            ("News", "https://example.com/news", "Info")
        ))

    install_http(monkeypatch, handler)
    assert len(web_search.search_web("Noticias de IA hoy")) == 1
    assert calls == ["news.google.com", "www.bing.com"]


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


def test_bad_news_xml_uses_generic_fallback(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "news.google.com":
            return httpx.Response(200, content=b"<rss><broken>")
        return httpx.Response(200, content=rss(
            ("Result", "https://example.com/valid", "OK")
        ))

    install_http(monkeypatch, handler)
    assert len(web_search.search_web("últimas noticias")) == 1
    assert calls == ["news.google.com", "www.bing.com"]


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


def test_sports_question_without_date_prefers_free_news(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        assert request.url.host == "news.google.com"
        return httpx.Response(200, content=rss(
            ("Resultado", "https://example.com/f1", "Resultado pendiente de verificar")
        ))

    install_http(monkeypatch, handler)
    results = web_search.search_web("¿Cómo salió la F1?")
    assert calls == ["news.google.com"]
    assert results[0]["url"] == "https://example.com/f1"


def test_semantic_current_query_without_date_prefers_free_news(monkeypatch):
    """The model can request fresh evidence using a query with no date words."""
    calls = []

    def handler(request):
        calls.append(request.url.host)
        assert request.url.host == "news.google.com"
        return httpx.Response(200, content=rss(
            ("Trámite", "https://example.com/tramite", "Requisitos por verificar")
        ))

    install_http(monkeypatch, handler)
    results = web_search.search_web("requisitos habilitación comercial", news_fallback=True)
    assert calls == ["news.google.com"]
    assert results[0]["url"] == "https://example.com/tramite"


def test_opaque_google_news_links_use_bounded_bing_direct_publisher_fallback(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "news.google.com":
            return httpx.Response(200, content=rss(*[
                (f"News {i}", f"https://news.google.com/rss/articles/{i}", f"Snippet {i}")
                for i in range(5)
            ]))
        return httpx.Response(200, content=rss(
            ("Direct 1", "https://publisher.example/story", "Publisher excerpt"),
            ("Direct 2", "https://other.example/story", "Other excerpt"),
            ("Duplicate", "https://publisher.example/story", "Repeat"),
        ))

    install_http(monkeypatch, handler)
    results = web_search.search_web("¿Cuándo juega River?")
    assert calls == ["news.google.com", "www.bing.com"]
    assert len(results) == 4
    assert [x["url"] for x in results][-2:] == [
        "https://publisher.example/story", "https://other.example/story"
    ]
    assert results[0]["title"] == "News 0"


def test_opaque_news_fallback_failure_preserves_news_snippets(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "news.google.com":
            return httpx.Response(200, content=rss(
                ("News", "https://news.google.com/rss/articles/opaque", "Snippet")
            ))
        return httpx.Response(503)

    install_http(monkeypatch, handler)
    results = web_search.search_web("cotización hoy")
    assert calls == ["news.google.com", "www.bing.com"]
    assert len(results) == 1
    assert results[0]["title"] == "News"
