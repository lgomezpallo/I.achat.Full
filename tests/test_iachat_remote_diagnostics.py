"""Offline tests for the read-only production incident diagnostic."""
import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError
from io import BytesIO

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "iachat_remote_diagnostics.py"
spec = importlib.util.spec_from_file_location("iachat_remote_diagnostics", SCRIPT)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def test_log_summary_never_repeats_secrets_or_user_messages():
    logs = (
        "user text=PRIVATE-CHAT-CONTENT token=SECRET-KEY providers_unavailable 429\n"
        "router_auth_rejected 401 password=DO-NOT-PRINT\n"
        "http 403 unrelated\n"
    )
    report = json.dumps(diag.summarize_logs(logs))
    assert "SECRET-KEY" not in report
    assert "PRIVATE-CHAT-CONTENT" not in report
    assert "DO-NOT-PRINT" not in report
    assert '"providers_unavailable": 1' in report
    assert '"router_auth_rejected": 1' in report
    assert '"http_429_mentions": 1' in report


def test_ready_probe_reports_only_allowlisted_metadata(monkeypatch):
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, *_): return b'{"mode":"integrated","token":"SECRET-KEY","status":"ready"}'
    monkeypatch.setattr(diag.urllib.request, "urlopen", lambda *a, **k: Response())
    assert diag.probe("/ready") == {"http": 200, "mode": "integrated"}


def test_not_ready_reports_safe_reason_only(monkeypatch):
    def fail(*_args, **_kwargs):
        raise HTTPError("http://127.0.0.1:8000/ready", 503, "error", {},
                        BytesIO(b'{"detail":"providers_not_configured","secret":"NEVER"}'))
    monkeypatch.setattr(diag.urllib.request, "urlopen", fail)
    assert diag.probe("/ready") == {"http": 503, "reason": "providers_not_configured"}


def test_report_has_no_inference_or_provider_calls(monkeypatch):
    seen = []
    def command(*args):
        seen.append(args)
        if args[0] == "journalctl":
            return True, "providers_failed 429 API_KEY=SECRET"
        if args[:2] == ("systemctl", "is-active"):
            return True, "active"
        return True, "/etc/systemd/system/iachat.service.d/20-integrated-providers.conf"
    monkeypatch.setattr(diag, "command", command)
    monkeypatch.setattr(diag, "probe", lambda path: {"http": 200} if path != "/api/router/status" else {"http": 401})
    monkeypatch.setattr(diag, "runtime_hash", lambda name: "abc123")
    report = diag.build_report()
    assert report["service"] == "active"
    assert report["private_router_status"] == {"http": 401}
    assert report["log_signals"]["http_429_mentions"] == 1
    assert "SECRET" not in json.dumps(report)
    assert all(args[0] in ("systemctl", "journalctl") for args in seen)
