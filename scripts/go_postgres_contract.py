"""PostgreSQL 16 contract test using G.O.'s real migrations in disposable CI.

No Oracle access, no external models, no production credentials or data.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from iachat.go_work_context import WorkContextUnavailable, official_context


def payload(message: str) -> dict:
    result = official_context(message)
    assert result is not None
    return json.loads(result.split(": ", 1)[1])


def main() -> None:
    admin_dsn = os.environ["GO_CONTRACT_ADMIN_DSN"]
    reader_dsn = os.environ["GO_WORK_READONLY_DSN"]
    migrations = Path(os.environ["GO_CONTRACT_MIGRATIONS"])
    # The test database exists only in the GitHub Actions PostgreSQL service.
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        for name in ("001_initial.sql", "002_passkeys.sql",
                     "003_attachments.sql", "004_chat_history.sql",
                     "005_flexible_records.sql", "006_flexible_chat_refs.sql"):
            conn.execute((migrations / name).read_text(encoding="utf-8"))
        conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        conn.execute("REVOKE CREATE ON DATABASE go_contract FROM PUBLIC")
        conn.execute("CREATE ROLE go_contract_reader LOGIN PASSWORD 'ci-only-reader'")
        conn.execute("GRANT CONNECT ON DATABASE go_contract TO go_contract_reader")
        conn.execute("GRANT USAGE ON SCHEMA public TO go_contract_reader")
        conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO go_contract_reader")
        first = conn.execute(
            "INSERT INTO obras (presupuesto,direccion,estado) "
            "VALUES (%s,%s,%s) RETURNING id",
            ("1093", "Rivadavia y Rodríguez Peña", "en_ejecucion"),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO obras (presupuesto,direccion,estado) VALUES (%s,%s,%s)",
            ("1190", "Alsina 354", "pendiente"),
        )
        conn.execute(
            "INSERT INTO go_record_types (nombre,version,esquema) "
            "VALUES (%s,%s,%s)",
            ("medicion", 1, Jsonb({"horas": {"tipo": "numero"}})),
        )
        original_id, corrected_id = uuid.uuid4(), uuid.uuid4()
        for action, proposal_id, event_id, replaces, hours in (
            ("record", uuid.uuid4(), original_id, None, 6),
            ("correct", uuid.uuid4(), corrected_id, original_id, 8),
        ):
            conn.execute(
                "INSERT INTO go_record_proposals "
                "(id,accion,tipo,version,presupuesto,datos,reemplaza,origen,situacion) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'confirmada')",
                (proposal_id, action, "medicion", 1, "1093",
                 Jsonb({"horas": hours}), replaces, "ci-disposable"),
            )
            conn.execute(
                "INSERT INTO go_record_events "
                "(id,propuesta_id,tipo,version,obra_id,datos,reemplaza) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (event_id, proposal_id, "medicion", 1, first,
                 Jsonb({"horas": hours}), replaces),
            )

    scoped = payload("¿Qué se registró en la obra 1093?")
    assert scoped["presupuesto"] == "1093" and scoped["estado"] == "en_ejecucion"
    assert len(scoped["registros"]) == 1
    assert scoped["registros"][0]["datos"]["horas"] == 8
    assert scoped["registros"][0]["id"] == str(corrected_id)
    overview = payload("¿Cuántas obras hay?")
    assert overview["total_obras"] == 2
    assert sum(x["cantidad"] for x in overview["por_estado"]) == 2
    comparison = payload("Compará obra 1093 y obra 1190")
    assert len(comparison["obras"]) == 2
    assert comparison["obras"][1]["presupuesto"] == "1190"
    assert comparison["obras"][1]["registros"] == []

    # The reader is genuinely read-only even outside the adapter's transaction.
    with psycopg.connect(reader_dsn) as conn:
        assert not conn.execute(
            "SELECT has_database_privilege(current_user,current_database(),'CREATE')"
        ).fetchone()[0]
        try:
            conn.execute(
                "INSERT INTO obras (presupuesto,direccion) VALUES ('999999','invalid')"
            )
        except psycopg.errors.InsufficientPrivilege:
            conn.rollback()
        else:
            raise AssertionError("reader unexpectedly wrote to obras")

    # The same adapter must reject the privileged writer account.
    os.environ["GO_WORK_READONLY_DSN"] = admin_dsn
    try:
        try:
            official_context("obra 1093")
        except WorkContextUnavailable as exc:
            assert str(exc) == "go_work_role_has_write_privileges"
        else:
            raise AssertionError("privileged account was accepted")
    finally:
        os.environ["GO_WORK_READONLY_DSN"] = reader_dsn

    print("GO_POSTGRES_CONTRACT=passed_real_postgres16_no_oracle_no_inference")


if __name__ == "__main__":
    main()
