"""Real PostgreSQL + HTTP chat + Router-transport contract, entirely offline.

Uses the original G.O. migrations in the disposable CI PostgreSQL service.
The Router HTTP response is deliberately simulated: this is NOT real inference,
not an Oracle E2E, and never sends work data to a provider.
"""
from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import psycopg
from fastapi.testclient import TestClient

from go_postgres_contract import main as check_postgres_contract


def main() -> None:
    # First verify real migrations, corrections, role grants and read-only SQL.
    check_postgres_contract()
    with tempfile.TemporaryDirectory(prefix="go-chat-contract-") as temp:
        os.environ.update({
            "IACHAT_PROFILE": "go-ute",
            "IACHAT_DB": os.path.join(temp, "labor-chat.sqlite"),
            "IACHAT_AUTH_SECRET": "ci-only-work-session-secret-longer-than-32",
            "IACHAT_GOOGLE_ALLOWED_SUBS": "ci-allowed-google-sub,ci-other-google-sub",
            "IACHAT_BACKEND": "router",
            # CI only: the HTTP Router response is mocked, never a provider call.
            "GO_ROUTER_INFERENCE_ENABLED": "1",
            "ROUTER_URL": "http://127.0.0.1:8010",
            "ROUTER_TOKEN": "ci-only-router-token",
            "GO_WORK_WRITE_ENABLED": "1",
            "GO_DATABASE_URL": os.environ["GO_CONTRACT_ADMIN_DSN"],
        })
        # No direct-provider credentials are needed or used in this test.
        for key in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "NVIDIA_API_KEY"):
            os.environ.pop(key, None)

        import iachat.app as app_module

        requests = []

        def fake_router_post(url, *, headers, json, timeout, follow_redirects, trust_env):
            assert url == "http://127.0.0.1:8010/route"
            assert headers == {"Authorization": "Bearer ci-only-router-token"}
            assert not follow_redirects and trust_env is False
            assert json["application_name"] == "go-ute"
            assert json["required_capabilities"] == ["chat"]
            assert json["images"] == []
            requests.append(json)
            last = json["task"]
            if "Registrá 16 horas ejecutadas en obra 1093" in last:
                # A real free model may wrap the action in one JSON fence.
                # The same HTTP approval flow must still stage, never commit.
                model_text = ('```json\n'
                              '{"go_intent":"v1","intent":"record","record_type":"medicion",'
                              '"budget":"1093","values":{"horas":16}}\n```')
            elif "Registrá 15 horas ejecutadas en obra 1093" in last:
                model_text = '{"go_intent":"v1","intent":"record","record_type":"medicion","budget":"1093","values":{"horas":15}}'
            elif "Registrá 99 horas en obra 1093" in last:
                model_text = '{"go_intent":"v1","intent":"record","record_type":"medicion","budget":"1190","values":{"horas":99}}'
            else:
                model_text = "Respuesta de Router simulado; no hay escritura oficial."
            return httpx.Response(
                200,
                json={"ok": True, "text": model_text},
                request=httpx.Request("POST", url),
            )

        def events_count():
            with psycopg.connect(os.environ["GO_CONTRACT_ADMIN_DSN"]) as conn:
                return conn.execute("SELECT COUNT(*) FROM go_record_events").fetchone()[0]

        assert events_count() == 2
        with (
            patch.object(app_module.google_oidc, "complete", side_effect=lambda code, state, flow: (
                "ci-other-google-sub" if code == "other" else "ci-allowed-google-sub"
            )),
            patch("iachat.web_planner.plan_web_lookup_semantic", return_value=SimpleNamespace(action="none")),
            patch("iachat.tool_planner.is_file_action_candidate", return_value=False),
            patch("iachat.auto_memory.learn", return_value=None),
            patch("iachat.backend.httpx.post", side_effect=fake_router_post),
        ):
            with TestClient(app_module.app, base_url="https://go.test") as client:
                unauthorized = client.post("/api/chat", json={"text": "obra 1093"})
                assert unauthorized.status_code == 401, unauthorized.text

                login = client.get(
                    "/auth/google/callback?code=ci&state=ci",
                    follow_redirects=False,
                )
                assert login.status_code == 303, login.text
                cookie = login.cookies.get("iachat_session")
                assert cookie

                first = client.post("/api/chat", json={
                    "text": "¿Qué se registró en la obra 1093?",
                })
                assert first.status_code == 200, first.text
                conversation_id = first.json()["conversation_id"]
                assert len(requests) == 1
                assert any(
                    '"horas": 8' in item["content"] and '"presupuesto": "1093"' in item["content"]
                    for item in requests[0]["conversation"]
                    if item["role"] == "user"
                )
                assert '"horas": 6' not in str(requests[0]["conversation"])
                assert any(
                    '"categorias_confirmadas"' in item["content"]
                    and '"version": 2' in item["content"]
                    and '"unidad": "h"' in item["content"]
                    for item in requests[0]["conversation"] if item["role"] == "user"
                ), "scoped chat needs confirmed metadata before proposing records"
                assert "NO modifica registros oficiales" in requests[0]["context"]

                followup = client.post("/api/chat", json={
                    "conversation_id": conversation_id,
                    "text": "¿Y qué se registró en esa obra?",
                })
                assert followup.status_code == 200, followup.text
                assert len(requests) == 2
                assert any(
                    '"presupuesto": "1093"' in item["content"]
                    for item in requests[1]["conversation"]
                    if item["role"] == "user"
                )

                proposed = client.post("/api/chat", json={
                    "conversation_id": conversation_id,
                    "text": "Registrá 10 horas ejecutadas para la obra 1093",
                })
                assert proposed.status_code == 200, proposed.text
                assert events_count() == 2, "chat must never silently write official events"

                # The SAME IAchat HTTP chat can stage a proposal through the
                # existing G.O. ledger; no event is written before approval.
                staged = client.post("/api/chat", json={
                    "conversation_id": conversation_id,
                    "text": "Registrá 15 horas ejecutadas en obra 1093",
                })
                assert staged.status_code == 200, staged.text
                proposal_id = staged.json()["history"][-1]["go_proposal_id"]
                assert "No está confirmado" in staged.json()["answer"]
                assert events_count() == 2

                # A second authorized Google account must never read or
                # approve the first worker's private conversation or proposal.
                # The official ledger and chat SQLite must agree on ownership.
                with TestClient(app_module.app, base_url="https://go.test") as other:
                    other_login = other.get(
                        "/auth/google/callback?code=other&state=ci",
                        follow_redirects=False,
                    )
                    assert other_login.status_code == 303, other_login.text
                    assert other.get("/api/conversations/" + conversation_id).status_code == 404
                    assert other.post("/api/chat", json={
                        "conversation_id": conversation_id,
                        "text": "dale",
                    }).status_code == 404
                    assert other.get("/api/conversations").json()["conversations"] == []
                    # The second user's own conversation cannot authorize a
                    # foreign proposal even if its UUID was disclosed.
                    cross_user = other.post("/api/chat", json={
                        "text": "Confirmo propuesta " + proposal_id,
                    })
                    assert cross_user.status_code == 200, cross_user.text
                    assert "no está pendiente en esta conversación" in cross_user.json()["answer"]
                    assert events_count() == 2

                # A UUID from another conversation cannot authorize a write.
                forged = client.post("/api/chat", json={
                    "text": "Confirmo propuesta " + proposal_id,
                })
                assert forged.status_code == 200, forged.text
                assert "no está pendiente en esta conversación" in forged.json()["answer"]
                assert events_count() == 2
                # Even a direct ledger call without the authenticated actor
                # cannot approve a labor-chat proposal. The DB row itself
                # enforces both identity and server-owned conversation.
                from go_ute import flexible
                assert flexible.decide(proposal_id, True)["phase"] == "unauthorized"
                assert events_count() == 2

                approved = client.post("/api/chat", json={
                    "conversation_id": conversation_id,
                    "text": "dale",
                })
                assert approved.status_code == 200, approved.text
                assert "confirmada" in approved.json()["answer"], approved.json()["answer"]
                assert events_count() == 3
                with psycopg.connect(os.environ["GO_CONTRACT_ADMIN_DSN"]) as conn:
                    assert conn.execute(
                        "SELECT datos FROM go_record_events WHERE propuesta_id=%s",
                        (proposal_id,),
                    ).fetchone() == ({"horas": 15},)
                    creator, scoped_conversation, decider = conn.execute(
                        "SELECT creado_por,origen_conversacion,decidido_por "
                        "FROM go_record_proposals WHERE id=%s", (proposal_id,),
                    ).fetchone()
                    assert creator and creator.startswith("g_")
                    assert scoped_conversation == conversation_id
                    assert decider == creator, "official change must be attributed to logged-in worker"

                # A short rejection must discard only the latest proposal
                # from this same authenticated conversation, with no event.
                pending_discard = client.post("/api/chat", json={
                    "conversation_id": conversation_id,
                    "text": "Registrá 16 horas ejecutadas en obra 1093",
                })
                assert pending_discard.status_code == 200, pending_discard.text
                assert "go_proposal_id" in pending_discard.json()["history"][-1]
                discarded = client.post("/api/chat", json={
                    "conversation_id": conversation_id,
                    "text": "no",
                })
                assert discarded.status_code == 200, discarded.text
                assert "descartada" in discarded.json()["answer"].lower()
                assert events_count() == 3

                # A repeated confirmation is not authorization for a second write.
                repeated = client.post("/api/chat", json={
                    "conversation_id": conversation_id,
                    "text": "Confirmo propuesta " + proposal_id,
                })
                assert repeated.status_code == 200, repeated.text
                assert events_count() == 3

                # Reject model-selected identity conflicting with the operator.
                mismatch = client.post("/api/chat", json={
                    "text": "Registrá 99 horas en obra 1093",
                })
                assert mismatch.status_code == 200, mismatch.text
                assert "no coincide" in mismatch.json()["answer"]
                assert events_count() == 3

                categories = client.post("/api/chat", json={
                    "text": "¿Qué categorías de registros están confirmadas?",
                })
                assert categories.status_code == 200, categories.text
                assert any(
                    '"consulta": "categorias_confirmadas"' in item["content"]
                    and '"version": 2' in item["content"]
                    and '"nombre": "medicion"' in item["content"]
                    for item in requests[-1]["conversation"]
                    if item["role"] == "user"
                )
                assert events_count() == 3

                # Natural follow-up: the operator replies with only the budget
                # after the server asks which work, never from model inference.
                before = len(requests)
                unclear = client.post("/api/chat", json={"text": "¿Qué pasó en esa obra?"})
                assert unclear.status_code == 200, unclear.text
                assert "¿A qué obra te referís?" in unclear.json()["answer"]
                assert len(requests) == before, "clarification must not call Router"
                resolved = client.post("/api/chat", json={
                    "conversation_id": unclear.json()["conversation_id"],
                    "text": "1093",
                })
                assert resolved.status_code == 200, resolved.text
                assert len(requests) == before + 1
                assert any(
                    '"presupuesto": "1093"' in item["content"]
                    for item in requests[-1]["conversation"] if item["role"] == "user"
                )
                assert events_count() == 3

            # Reopen the same isolated work SQLite with the authenticated cookie.
            with TestClient(app_module.app, base_url="https://go.test") as reopened:
                reopened.cookies.set("iachat_session", cookie)
                saved = reopened.get("/api/conversations/" + conversation_id)
                assert saved.status_code == 200, saved.text
                assert len(saved.json()["history"]) == 16
                assert events_count() == 3

    print("GO_HTTP_POSTGRES_CONTRACT=passed_real_postgres16_staging_approval_isolated_simulated_router_no_oracle_no_inference")


if __name__ == "__main__":
    main()
