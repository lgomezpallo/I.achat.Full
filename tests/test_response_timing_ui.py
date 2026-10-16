from iachat.web import HTML


def test_response_timing_uses_monotonic_clock_and_argentina_timezone():
    assert "var requestStartedAt=performance.now()" in HTML
    assert "performance.now()-requestStartedAt" in HTML
    assert "America/Argentina/Buenos_Aires" in HTML
    assert "addResponseTiming(responseNode" in HTML


def test_timing_is_not_added_to_error_messages():
    assert "if(!r.ok)" in HTML
    assert "addResponseTiming(responseNode" in HTML
    assert "meta.textContent=clock+" in HTML
