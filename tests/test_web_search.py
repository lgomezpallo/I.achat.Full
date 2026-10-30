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


def test_opaque_google_news_retains_explicit_rss_publisher(monkeypatch):
    def handler(request):
        return httpx.Response(200, content=(
            b"<rss><channel><item><title>Agenda</title>"
            b"<link>https://news.google.com/rss/articles/abc</link>"
            b"<description>Fecha por verificar</description>"
            b"<source url='https://diario.example.com'>Diario Uno</source>"
            b"</item></channel></rss>"
        ))

    install_http(monkeypatch, handler)
    results = web_search._fetch_feed(
        web_search.GOOGLE_NEWS_RSS, {"q": "agenda"}, 2.0
    )
    assert results[0]["rss_publisher"] == "Diario Uno"
    assert results[0]["url"].startswith("https://news.google.com/")


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
            ("Partido", "https://example.com/partido", "Horario por confirmar")
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


def test_opaque_google_news_links_use_only_relevant_direct_publisher_fallback(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "news.google.com":
            return httpx.Response(200, content=rss(*[
                (f"News {i}", f"https://news.google.com/rss/articles/{i}", f"Snippet {i}")
                for i in range(5)
            ]))
        return httpx.Response(200, content=rss(
            ("Mapa de restaurantes", "https://maps.example/restaurants", "Direcciones y opiniones"),
            ("Precios de combustibles en Argentina", "https://publisher.example/story",
             "Precios de combustibles Argentina hoy"),
            ("Precio combustibles hoy", "https://other.example/story",
             "Valores de combustibles Argentina"),
            ("Duplicado", "https://publisher.example/story", "Repetido"),
        ))

    install_http(monkeypatch, handler)
    results = web_search.search_web("precios combustibles Argentina hoy")
    assert calls == ["news.google.com", "www.bing.com"]
    assert len(results) == 5
    assert [x["url"] for x in results][-2:] == [
        "https://publisher.example/story", "https://other.example/story"
    ]
    assert "https://maps.example/restaurants" not in [x["url"] for x in results]
    assert results[0]["title"] == "News 0"


def test_four_direct_publishers_can_be_attempted_before_opaque_proxies(monkeypatch):
    """One blocked publisher must not exhaust all page candidates."""
    def handler(request):
        if request.url.host == "news.google.com":
            return httpx.Response(200, content=rss(*[
                (f"Google {i}", f"https://news.google.com/rss/articles/{i}", "River Plate próximo partido fecha horario")
                for i in range(5)
            ]))
        return httpx.Response(200, content=rss(*[
            (f"River Plate próximo partido fecha horario {i}",
             f"https://publisher{i}.example.com/river",
             "River Plate próximo partido fecha horario confirmado por fuente")
            for i in range(5)
        ]))

    install_http(monkeypatch, handler)
    results = web_search.search_web("River Plate próximo partido fecha horario", news_fallback=True)
    assert len(results) == 5
    assert sum("publisher" in item["url"] for item in results) == 4
    assert sum("news.google.com" in item["url"] for item in results) == 1


def test_news_fallback_keeps_entity_match_without_temporal_words(monkeypatch):
    """News publisher titles need not repeat generic query words like semana."""
    paths = []
    def handler(request):
        paths.append(request.url.path)
        if request.url.host == "news.google.com":
            return httpx.Response(200, content=rss(*[
                (f"Google {i}", f"https://news.google.com/rss/articles/{i}", "Resumen")
                for i in range(5)
            ]))
        assert request.url.path == "/news/search"
        return httpx.Response(200, content=rss(
            ("ANSES informó nuevas fechas de pago", "https://publisher.example.com/anses",
             "Los beneficiarios de ANSES reciben novedades"),
            ("Cartelera de cine", "https://cinema.example.com/film", "Estrenos y reseñas"),
        ))

    install_http(monkeypatch, handler)
    results = web_search.search_web("ANSES novedades esta semana", news_fallback=True)
    assert paths == ["/rss/search", "/news/search"]
    assert any(item["url"] == "https://publisher.example.com/anses" for item in results)
    assert all("cinema.example.com" not in item["url"] for item in results)


def test_irrelevant_direct_fallback_keeps_news_instead_of_padding_sources(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "news.google.com":
            return httpx.Response(200, content=rss(
                ("Noticia 1", "https://news.google.com/rss/articles/a", "Texto 1"),
                ("Noticia 2", "https://news.google.com/rss/articles/b", "Texto 2"),
            ))
        return httpx.Response(200, content=rss(
            ("Movie listings", "https://cinema.example/movies", "Film reviews"),
            ("Map locations", "https://maps.example/places", "Restaurants"),
        ))

    install_http(monkeypatch, handler)
    results = web_search.search_web("cotización dólar oficial Argentina hoy")
    assert calls == ["news.google.com", "www.bing.com", "www.bing.com"]
    assert len(results) == 2
    assert all(item["url"].startswith("https://news.google.com/") for item in results)


def test_direct_fallback_relevance_is_general_and_accent_insensitive():
    candidate = {
        "title": "Cotizacion del dolar oficial",
        "snippet": "Argentina: precio actualizado",
    }
    assert web_search._relevant_direct_fallback(
        candidate, "cotización dólar oficial Argentina hoy"
    )
    assert not web_search._relevant_direct_fallback(
        {"title": "Información de mapas", "snippet": "Ubicaciones de Argentina"},
        "cotización dólar oficial Argentina hoy",
    )


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
    assert calls == ["news.google.com", "www.bing.com", "www.bing.com"]
    assert len(results) == 1
    assert results[0]["title"] == "News"


def test_opaque_google_news_uses_bing_news_publisher_urls_not_click_wrappers(monkeypatch):
    """Live-shaped Bing News RSS click URLs must become safe publisher URLs."""
    from urllib.parse import quote

    requests = []

    def handler(request):
        requests.append((request.url.host, request.url.path))
        if request.url.host == "news.google.com":
            return httpx.Response(200, content=rss(
                ("River", "https://news.google.com/rss/articles/opaque", "Noticia"),
            ))
        assert request.url.path == "/news/search"
        direct = "https://diario.example.com/deportes/river-partido"
        wrapped = ("https://www.bing.com/news/apiclick.aspx?ref=abc&url="
                   + quote(direct, safe="") + "&foo=bar")
        return httpx.Response(200, content=rss(
            ("River Plate próximo partido", wrapped.replace("&", "&amp;"), "Fecha River Plate por confirmar"),
            ("Enlace privado", "https://www.bing.com/news/apiclick.aspx?url=http%3A%2F%2F127.0.0.1%2Fprivate",
             "River Plate próximo partido"),
        ))

    install_http(monkeypatch, handler)
    results = web_search.search_web("próximo partido River Plate")
    assert requests == [
        ("news.google.com", "/rss/search"),
        ("www.bing.com", "/news/search"),
    ]
    assert [item["url"] for item in results] == [
        "https://news.google.com/rss/articles/opaque",
        "https://diario.example.com/deportes/river-partido",
    ]


def test_news_fallback_without_google_results_uses_bing_news_not_generic(monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.host == "news.google.com":
            return httpx.Response(503)
        return httpx.Response(200, content=rss(
            ("Precio dólar oficial", "https://finanzas.example.com/cotizacion", "Cotización del día")
        ))

    install_http(monkeypatch, handler)
    results = web_search.search_web("dólar oficial hoy")
    assert paths == ["/rss/search", "/news/search"]
    assert results[0]["url"] == "https://finanzas.example.com/cotizacion"


def test_bing_news_wrapper_rejects_multiple_or_non_https_destinations():
    base = "https://www.bing.com/news/apiclick.aspx?"
    assert web_search._bing_news_publisher_url(base + "url=https%3A%2F%2Fexample.com%2Fa&url=https%3A%2F%2Fevil.example%2F") == ""
    assert not web_search._public_https_link(
        web_search._bing_news_publisher_url(base + "url=http%3A%2F%2F127.0.0.1%2F")
    )


def test_legacy_http_bing_click_wrapper_is_never_fetched_and_safe_target_is_https():
    from urllib.parse import quote
    direct = "https://publisher.example.com/nota?fecha=2026-10-30"
    wrapper = "http://www.bing.com/news/apiclick.aspx?ref=feed&url=" + quote(direct, safe="")
    assert web_search._bing_news_publisher_url(wrapper) == direct
    old_article = "http://publisher.example.com/nota"
    wrapper = "http://www.bing.com/news/apiclick.aspx?url=" + quote(old_article, safe="")
    assert web_search._bing_news_publisher_url(wrapper) == "https://publisher.example.com/nota"
    unsafe = "http://127.0.0.1/private"
    wrapper = "http://www.bing.com/news/apiclick.aspx?url=" + quote(unsafe, safe="")
    assert web_search._bing_news_publisher_url(wrapper) == ""
    unsafe_port = "http://publisher.example.com:8080/private"
    wrapper = "http://www.bing.com/news/apiclick.aspx?url=" + quote(unsafe_port, safe="")
    assert web_search._bing_news_publisher_url(wrapper) == ""


def test_primary_rss_rejects_irrelevant_chinese_results(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(200, content=rss(
            ("WhatsApp 更新的中文消息", "https://zhihu.com/p/abc", "最新的中文内容和讨论"),
            ("Actualización de requisitos ANSES octubre 2026",
             "https://example.com/anses", "ANSES requisitos y calendario octubre 2026"),
        ))

    install_http(monkeypatch, handler)
    results = web_search.search_web("requisitos ANSES calendario octubre 2026", news_fallback=True)
    assert calls == ["news.google.com"]
    assert [item["url"] for item in results] == ["https://example.com/anses"]


def test_primary_rss_rejects_long_query_without_content_overlap():
    assert not web_search._plausibly_relevant(
        {"title": "Noticias sobre WhatsApp", "snippet": "Actualización de aplicaciones"},
        "requisitos ANSES calendario octubre 2026",
    )
    assert web_search._plausibly_relevant(
        {"title": "ANSES calendario octubre 2026", "snippet": "Pagos y requisitos"},
        "requisitos ANSES calendario octubre 2026",
    )
    # Explicit requests for another language may use that script.
    assert web_search._plausibly_relevant(
        {"title": "中文新闻资讯", "snippet": "中文网站和内容"},
        "noticias en chino",
    )
