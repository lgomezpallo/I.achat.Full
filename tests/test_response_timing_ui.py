from iachat.web import HTML


def test_response_timing_uses_monotonic_clock_and_argentina_timezone():
    assert "var requestStartedAt=performance.now()" in HTML
    assert "performance.now()-requestStartedAt" in HTML
    assert "America/Argentina/Buenos_Aires" in HTML
    assert "addAssistantMetadata(responseNode" in HTML


def test_timing_is_not_added_to_error_messages():
    assert "if(!r.ok)" in HTML
    assert "addAssistantMetadata(responseNode" in HTML
    assert "meta.textContent=clock+" in HTML


def test_sources_and_timing_rehydrate_from_same_history_metadata():
    assert "if(m.role==='assistant')addAssistantMetadata(node,m.web_sources,m.elapsed_ms,m.completed_at)" in HTML
    assert "lastMessage.web_sources||d.web_sources" in HTML
    assert "lastMessage.completed_at||new Date().toISOString()" in HTML
    assert "if(sourcesBox.querySelector('a'))node.append(sourcesBox)" in HTML
