"""Offline tests for the read-only production incident diagnostic."""
import importlib.util
import hashlib
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
    assert all(args[0] in ("systemctl", "journalctl", "git") for args in seen)


def test_web_pipeline_fingerprints_distinguish_unreleased_code(monkeypatch, tmp_path):
    """Presence/hash of web modules is observable without accessing user data."""
    monkeypatch.setattr(diag, "APP", tmp_path)
    module_dir = tmp_path / "iachat"
    module_dir.mkdir()
    (module_dir / "web_search.py").write_text("legacy RSS only\n")
    (module_dir / "web_planner.py").write_text("semantic decision\n")
    assert diag.runtime_hash("web_research.py") is None
    assert diag.runtime_hash("web_search.py") == hashlib.sha256(b"legacy RSS only\n").hexdigest()
    assert diag.runtime_hash("web_planner.py") == hashlib.sha256(b"semantic decision\n").hexdigest()


def test_report_includes_web_pipeline_hashes_without_reading_secrets(monkeypatch):
    monkeypatch.setattr(diag, "command", lambda *args: (True, "active"))
    monkeypatch.setattr(diag, "probe", lambda path: {"http": 200})
    seen = []
    def fingerprint(name):
        seen.append(name)
        return None if name in ("web_planner.py", "web_research.py") else "fake-code-hash"
    monkeypatch.setattr(diag, "runtime_hash", fingerprint)
    report = diag.build_report()
    assert report["runtime_sha256"] == {
        "app_py": "fake-code-hash",
        "backend_py": "fake-code-hash",
        "web_search_py": "fake-code-hash",
        "web_planner_py": None,
        "web_research_py": None,
    }
    assert set(seen) == {
        "app.py", "backend.py", "web_search.py", "web_planner.py", "web_research.py"
    }
    assert "not necessarily the code loaded" in report["interpretation"]


def test_checkout_commit_is_allowlisted_and_not_confused_with_loaded_code(monkeypatch):
    """Only a 40-character git revision may appear; checkout is not process proof."""
    def make_command(revision):
        def fake_command(*args):
            if args[:2] == ("git", "-C"):
                return True, revision
            if args[:2] == ("systemctl", "is-active"):
                return True, "active"
            return True, ""
        return fake_command
    monkeypatch.setattr(diag, "probe", lambda path: {"http": 200})
    monkeypatch.setattr(diag, "runtime_hash", lambda name: None)
    valid = "a" * 40
    monkeypatch.setattr(diag, "command", make_command(valid))
    assert diag.build_report()["checkout_commit"] == valid
    monkeypatch.setattr(diag, "command", make_command("token=SECRET-PRODUCTION"))
    report = diag.build_report()
    assert report["checkout_commit"] is None
    assert "SECRET-PRODUCTION" not in json.dumps(report)
    assert "not necessarily the code loaded" in report["interpretation"]


def test_oracle_diagnostic_requires_explicit_manual_dispatch():
    """No PR/push event may automatically open SSH with production secrets."""
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "oracle-status.yml").read_text()
    triggers = workflow.split("\\non:\\n", 1)[1].split("\\npermissions:", 1)[0]
    assert "  workflow_dispatch:" in triggers
    for event in ("push:", "pull_request:", "workflow_run:", "schedule:"):
        assert event not in triggers
    assert "environment: oracle-production" in workflow
    assert "bash scripts/diagnostico_oracle.sh" in workflow
