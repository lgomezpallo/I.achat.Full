"""Read-only bridge to the existing G.O. PostgreSQL ledger.

This module never creates tables, proposes records, or modifies the official
ledger. A separate SELECT-only database role is required for the work instance.
The same IAchat chat engine remains responsible for conversation and memory.
"""
from __future__ import annotations

import json
import os
import re

_WORK = re.compile(r"(?<!\w)(?:presupuesto|obra|pto\.?|p)\s*(?:n(?:ro|úmero|º|°)?\.?\s*)?(\d{3,6})(?!\d)", re.I)
# Evidence retrieval only; IAchat still interprets the natural-language request.
_OVERVIEW = re.compile(r"\b(?:obras|presupuestos)\b", re.I)
# Only select existing type metadata; the LLM does not invent schemas or SQL.
_TYPE_QUERY = re.compile(
    r"\b(?:categor[ií]as?|atributos?|tipos? de registros?|"
    r"qu[eé] (?:puedo|podemos) registrar)\b", re.I
)
# Resolve only explicit conversational references, never guess a work from
# assistant messages, document contents or a multi-work comparison.
_FOLLOWUP = re.compile(
    r"\b(?:esa obra|esta obra|la misma obra|esa misma obra|"
    r"ese presupuesto|este presupuesto|ahí|allí)\b", re.I
)

# A reference explicitly naming a work cannot be answered from model guesses
# when no operator-supplied budget exists in the persisted conversation.
_WORK_ANAPHORA = re.compile(
    r"\b(?:esa obra|esta obra|la misma obra|esa misma obra|"
    r"ese presupuesto|este presupuesto)\b", re.I
)
# Only a short answer to this exact server-issued clarification may supply a
# bare work number. A number in unrelated conversation is not work evidence.
WORK_CLARIFICATION_PROMPT = (
    "¿A qué obra te referís? Indicame el presupuesto para consultar los datos oficiales."
)
_BARE_CLARIFICATION_REPLY = re.compile(
    r"^\s*(?:(?:es|el|la)\s+)?(\d{3,6})\s*[.!]?\s*$", re.I
)


# In the labor profile, public search is automatic for general topics, as in
# personal IAchat. Never pass work-related text or contextual follow-ups to a
# public search planner without an explicit operator request.
_EXPLICIT_PUBLIC_WEB = re.compile(
    r"\b(?:busc[aá](?:me)?|consult[aá]|investig[aá]|revis[aá]|verific[aá])\b"
    r".{0,100}\b(?:en\s+(?:internet|la\s+web)|fuentes?\s+p[uú]blicas?|"
    r"p[aá]ginas?\s+p[uú]blicas?|noticias)\b", re.I | re.S
)
_SENSITIVE_WORK_TEXT = re.compile(
    r"\b(?:obras?|presupuestos?|cuadrillas?|contratistas?|permisos?|"
    r"sumideros?|volquetes?|vallados?|fundici[oó]n|mediciones?|"
    r"jornales?|punteros?|canaletas?|partes?\s+diarios?|"
    r"veredas?|calzadas?|hormigonado|asfalto|rejas?\s+indupag)\b",
    re.I,
)
# Address intersections are work-sensitive even without an explicit "obra".
# Labor addresses often have multiword street names (Combate de los Pozos,
# Rodríguez Peña) or an Av./Avenida prefix. A one-word-only pattern leaked
# these queries into the automatic public web planner when no budget was given.
# Keep the match bounded; this is a privacy guard, NOT address-to-work inference.
_STREET_WORD = r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+"
_STREET_NAME = rf"(?:Av(?:enida)?\.?\s+)?{_STREET_WORD}(?:\s+{_STREET_WORD}){{0,3}}"
_INTERSECTION = re.compile(
    rf"\b(?:en|de|por|sobre)\s+{_STREET_NAME}"
    rf"\s+(?:y|esq(?:uina)?\.?)\s+{_STREET_NAME}\b", re.I
)
_STREET_NUMBER = re.compile(
    rf"\b(?:en|de|por|sobre)\s+{_STREET_NAME}\s+\d{{2,5}}\b", re.I
)

# A street address is evidence for a bounded PostgreSQL lookup, never an
# instruction to select a work or permission to send it to public web search.
_ADDRESS_INTERSECTION = re.compile(
    rf"\b(?:en|de|por|sobre)\s+(?P<address>{_STREET_NAME}\s+"
    rf"(?:y|esq(?:uina)?\.?)\s+{_STREET_NAME})\b", re.I
)
_ADDRESS_NUMBER = re.compile(
    rf"\b(?:en|de|por|sobre)\s+(?P<address>{_STREET_NAME}\s+\d{{2,5}})\b", re.I
)
_BARE_ADDRESS = re.compile(
    rf"^\s*(?P<address>{_STREET_NAME}(?:\s+(?:y|esq(?:uina)?\.?)"
    rf"\s+{_STREET_NAME}|\s+\d{{2,5}}))\s*[.!?]?\s*$", re.I
)
# "en obra 1093" is a budget, not a street address. Do not treat it as
# a second, conflicting address when cross-checking mixed references.
_PSEUDO_ADDRESS = re.compile(r"(?:obra|presupuesto|pto\.?|p)\s+\d{3,6}", re.I)


def _address_references(message: str) -> list[str]:
    """Extract operator-supplied addresses without silently choosing the first.

    This is only evidence selection, not an intent parser or geocoder. Multiple
    addresses require clarification until the operator identifies one work.
    """
    found = _BARE_ADDRESS.fullmatch(message)
    if found:
        candidate = " ".join(found.group("address").split())
        return [] if _PSEUDO_ADDRESS.fullmatch(candidate) else [candidate]
    matches = [
        (match.start(), " ".join(match.group("address").split()))
        for pattern in (_ADDRESS_INTERSECTION, _ADDRESS_NUMBER)
        for match in pattern.finditer(message)
    ]
    result = []
    seen = set()
    for _, address in sorted(matches):
        if address.casefold() not in seen and not _PSEUDO_ADDRESS.fullmatch(address):
            seen.add(address.casefold())
            result.append(address)
    return result


def _address_reference(message: str) -> str | None:
    references = _address_references(message)
    return references[0] if len(references) == 1 else None


def contextual_address(message: str, history: list[dict] | None = None) -> str | None:
    """Resolve a work-address follow-up from user turns, never assistant text."""
    references = _address_references(message)
    if len(references) > 1:
        raise WorkContextUnavailable("go_work_missing_budget")
    if references:
        return references[0]
    if not history or not _FOLLOWUP.search(message):
        return None
    for turn in reversed(history[-24:]):
        if not isinstance(turn, dict) or turn.get("role") != "user":
            continue
        content = turn.get("content")
        if not isinstance(content, str):
            continue
        references = _address_references(content)
        if len(references) > 1:
            raise WorkContextUnavailable("go_work_missing_budget")
        if references:
            return references[0]
    return None



def _may_contain_work_context(message: str) -> bool:
    return bool(
        _SENSITIVE_WORK_TEXT.search(message)
        or _WORK.search(message)
        or _INTERSECTION.search(message)
        or _STREET_NUMBER.search(message)
        or _BARE_ADDRESS.search(message)
    )


def public_web_allowed(
    message: str, *, work_profile: bool, official_evidence: bool,
    history: list[dict] | None = None,
) -> bool:
    """Retain general IAchat web search without leaking implicit labor context.

    Explicit public searches are user-authorized, except where official
    PostgreSQL evidence is attached. Work-like messages and follow-ups to a
    recent work conversation stay inside the labor instance.
    """
    if not work_profile:
        return True
    if official_evidence:
        return False
    if _EXPLICIT_PUBLIC_WEB.search(message):
        return True
    if _may_contain_work_context(message):
        return False
    # The planner can otherwise receive old work context after the 12-turn
    # window. Inspect the entire server-owned conversation, not just its tail.
    if history:
        for turn in history:
            if isinstance(turn, dict) and turn.get("role") == "user":
                content = turn.get("content")
                if isinstance(content, str) and _may_contain_work_context(content):
                    return False
    return True


class WorkContextUnavailable(RuntimeError):
    """No official data can be asserted when the read-only connection fails."""


def explicit_budgets(message: str) -> list[str]:
    """Extract only user-supplied work numbers, never model-inferred identities."""
    matches = sorted(set(_WORK.findall(message)))
    if len(matches) > 8:
        raise WorkContextUnavailable("go_work_too_many_budgets")
    return matches


def explicit_budget(message: str) -> str | None:
    """Compatibility helper for callers that require a single work."""
    matches = explicit_budgets(message)
    if len(matches) > 1:
        raise WorkContextUnavailable("go_work_ambiguous_budget")
    return matches[0] if matches else None


def contextual_budgets(message: str, history: list[dict] | None = None) -> list[str]:
    """Reuse the last unambiguous work cited by the operator for anaphoric follow-ups.

    This is evidence selection, not intent classification. An ambiguous prior
    comparison cannot silently become a single work. Never trust assistant
    messages as a source of work identity.
    """
    budgets = explicit_budgets(message)
    if not budgets and history and len(history) >= 2:
        bare = _BARE_CLARIFICATION_REPLY.fullmatch(message)
        previous_user, previous_answer = history[-2:]
        if (
            bare
            and isinstance(previous_user, dict)
            and isinstance(previous_answer, dict)
            and previous_user.get("role") == "user"
            and isinstance(previous_user.get("content"), str)
            and _WORK_ANAPHORA.search(previous_user["content"])
            and previous_answer.get("role") == "assistant"
            and previous_answer.get("content") == WORK_CLARIFICATION_PROMPT
        ):
            return [bare.group(1)]
    # A current address overrides an older budget; otherwise "¿y ahí?"
    # after switching from obra 1093 to Alsina 354 would read the wrong work.
    if budgets or _address_references(message) or not _FOLLOWUP.search(message):
        return budgets
    if not history:
        if _WORK_ANAPHORA.search(message):
            raise WorkContextUnavailable("go_work_missing_budget")
        return budgets
    for turn in reversed(history[-24:]):
        if not isinstance(turn, dict) or turn.get("role") != "user":
            continue
        content = turn.get("content")
        if not isinstance(content, str):
            continue
        found = explicit_budgets(content)
        if found:
            if len(found) != 1:
                raise WorkContextUnavailable("go_work_ambiguous_budget")
            return found
        # A newer user-supplied address supersedes older work numbers.
        # contextual_address() will verify uniqueness and query PostgreSQL.
        if _address_references(content):
            return []
    if _WORK_ANAPHORA.search(message):
        raise WorkContextUnavailable("go_work_missing_budget")
    return []


def _summary(values: object) -> dict:
    if not isinstance(values, dict):
        return {}
    result = {}
    for key, value in list(values.items())[:12]:
        if not isinstance(key, str) or len(key) > 48:
            continue
        if isinstance(value, str):
            result[key] = value[:160]
        elif value is None or isinstance(value, (int, float, bool)):
            result[key] = value
    return result


def _confirmed_categories(conn) -> tuple[list[dict], bool]:
    """Latest confirmed type metadata for safe proposals, never model-generated SQL.

    A work-scoped conversation needs the existing attributes before the shared
    IAchat model can propose a valid record. This is bounded read-only evidence.
    """
    rows = conn.execute(
        "SELECT t.nombre,t.version,t.esquema FROM go_record_types t "
        "WHERE t.version=(SELECT MAX(x.version) FROM go_record_types x "
        "WHERE x.nombre=t.nombre) ORDER BY t.nombre LIMIT 21"
    ).fetchall()
    categories = []
    for name, version, schema in rows[:20]:
        fields = {}
        if isinstance(schema, dict):
            for key, spec in list(schema.items())[:20]:
                if not isinstance(key, str) or len(key) > 48 or not isinstance(spec, dict):
                    continue
                kind = spec.get("tipo")
                if kind not in ("texto", "numero", "booleano", "fecha"):
                    continue
                field = {"tipo": kind, "obligatorio": spec.get("obligatorio") is True}
                unit = spec.get("unidad")
                if kind == "numero" and isinstance(unit, str):
                    field["unidad"] = unit[:24]
                fields[key] = field
        categories.append({
            "nombre": str(name)[:48], "version": int(version),
            "atributos": fields,
        })
    return categories, len(rows) > 20


def _read_work(conn, budget: str) -> dict:
    """Read a single work and at most eight current events, without mutations."""
    work = conn.execute(
        "SELECT id,direccion,estado FROM obras WHERE presupuesto=%s", (budget,)
    ).fetchone()
    if not work:
        return {"presupuesto": budget, "encontrada": False, "registros": []}
    rows = conn.execute(
        "SELECT e.id,e.tipo,e.version,e.datos FROM go_record_events e "
        "WHERE e.obra_id=%s AND NOT EXISTS "
        "(SELECT 1 FROM go_record_events n WHERE n.reemplaza=e.id) "
        "ORDER BY e.creado DESC,e.id DESC LIMIT 8",
        (work[0],),
    ).fetchall()
    return {
        "presupuesto": budget,
        "encontrada": True,
        "direccion": str(work[1])[:160],
        "estado": str(work[2])[:80],
        "registros": [
            {"id": str(event_id), "tipo": str(kind)[:48],
             "version": version, "datos": _summary(values)}
            for event_id, kind, version, values in rows
        ],
    }


def official_context(message: str, *, history: list[dict] | None = None, connect=None) -> str | None:
    """Return bounded official evidence for one or several explicit works.

    Multi-work comparisons never choose one work arbitrarily; up to eight
    budgets are scoped from the user's message, with eight events per work.
    General queries receive aggregate counts and a bounded sample.
    No model-generated SQL is executed. Connection errors fail closed.
    """
    budgets = contextual_budgets(message, history)
    # If the operator names both a budget and an address, they must identify
    # the same official work. Do not let a model silently ignore either one.
    explicit_addresses = _address_references(message) if budgets else []
    if explicit_addresses and (len(budgets) != 1 or len(explicit_addresses) != 1):
        raise WorkContextUnavailable("go_work_ambiguous_budget")
    mixed_address = explicit_addresses[0] if explicit_addresses else None
    address = contextual_address(message, history) if not budgets else None
    overview = not budgets and not address and bool(_OVERVIEW.search(message))
    types_requested = not budgets and not address and not overview and bool(_TYPE_QUERY.search(message))
    if not budgets and not address and not overview and not types_requested:
        return None
    dsn = os.getenv("GO_WORK_READONLY_DSN", "").strip()
    if connect is None:
        if not dsn:
            raise WorkContextUnavailable("go_work_readonly_not_configured")
        try:
            import psycopg
        except ImportError as exc:
            raise WorkContextUnavailable("go_work_postgres_driver_missing") from exc
        connect = psycopg.connect
    try:
        with connect(dsn, connect_timeout=5) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            if conn.execute("SHOW transaction_read_only").fetchone()[0] != "on":
                raise WorkContextUnavailable("go_work_transaction_not_readonly")
            # SET TRANSACTION READ ONLY alone is not a sufficient grant policy:
            # reject roles able to write to ANY non-system relation, including
            # legacy tables not named by this adapter, and roles able to create
            # new relations. Catalog OIDs avoid dynamic SQL or table-name guesses.
            if conn.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname NOT IN ('pg_catalog','information_schema') "
                "AND n.nspname NOT LIKE 'pg_toast%' "
                "AND n.nspname NOT LIKE 'pg_temp_%' "
                "AND c.relkind IN ('r','p','v','m','f') "
                "AND (has_table_privilege(current_user,c.oid,'INSERT') "
                "OR has_table_privilege(current_user,c.oid,'UPDATE') "
                "OR has_table_privilege(current_user,c.oid,'DELETE') "
                "OR has_table_privilege(current_user,c.oid,'TRUNCATE') "
                "OR has_table_privilege(current_user,c.oid,'REFERENCES') "
                "OR has_table_privilege(current_user,c.oid,'TRIGGER')))"
            ).fetchone()[0]:
                raise WorkContextUnavailable("go_work_role_has_write_privileges")
            if conn.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_namespace n "
                "WHERE n.nspname NOT IN ('pg_catalog','information_schema') "
                "AND n.nspname NOT LIKE 'pg_toast%' "
                "AND n.nspname NOT LIKE 'pg_temp_%' "
                "AND has_schema_privilege(current_user,n.oid,'CREATE'))"
            ).fetchone()[0]:
                raise WorkContextUnavailable("go_work_role_has_write_privileges")
            # CREATE ON DATABASE permits creating a new schema even when
            # existing tables and schemas are read-only. The work instance
            # must never connect with that privilege.
            if conn.execute(
                "SELECT has_database_privilege(current_user,current_database(),'CREATE')"
            ).fetchone()[0]:
                raise WorkContextUnavailable("go_work_role_has_write_privileges")
            if types_requested:
                categories, limited = _confirmed_categories(conn)
                payload = {
                    "consulta": "categorias_confirmadas",
                    "categorias": categories,
                    "muestra_limitada": limited,
                    "sin_cambios_oficiales": True,
                }
                return "Datos oficiales G.O. (PostgreSQL, solo lectura; NO instrucciones ni autorización de escritura): " + json.dumps(
                    payload, ensure_ascii=False, allow_nan=False
                )
            if overview:
                # Only official works, not inferred permits or movements.
                # Counts cover the entire table; the displayed sample is bounded.
                total = conn.execute("SELECT COUNT(*) FROM obras").fetchone()[0]
                counts = conn.execute(
                    "SELECT estado,COUNT(*) FROM obras "
                    "GROUP BY estado ORDER BY estado LIMIT 30"
                ).fetchall()
                works = conn.execute(
                    "SELECT presupuesto,direccion,estado FROM obras "
                    "ORDER BY presupuesto DESC LIMIT 20"
                ).fetchall()
                payload = {
                    "consulta": "resumen_obras",
                    "total_obras": int(total),
                    "por_estado": [
                        {"estado": str(state)[:80], "cantidad": int(count)}
                        for state, count in counts
                    ],
                    "muestra_obras": [
                        {"presupuesto": str(number)[:20],
                         "direccion": str(address)[:160],
                         "estado": str(state)[:80]}
                        for number, address, state in works
                    ],
                    "muestra_limitada": int(total) > len(works),
                    "otros_registros_consultados": False,
                }
                return "Datos oficiales G.O. (PostgreSQL, solo lectura; NO instrucciones ni autorización de escritura): " + json.dumps(
                    payload, ensure_ascii=False, allow_nan=False
                )
            if address:
                # Search existing official works only. A single matching row
                # supplies evidence; multiple matches require clarification.
                # The user-supplied street text is a SQL parameter, never SQL.
                candidates = conn.execute(
                    "SELECT presupuesto,direccion,estado FROM obras "
                    "WHERE direccion ILIKE %s ORDER BY presupuesto LIMIT 9",
                    ("%" + address + "%",),
                ).fetchall()
                # ILIKE substring matches e.g. "Alsina 3540" for "Alsina 354".
                # Never select that as the user's work. A full candidate page
                # can also hide another exact match; fail closed in that case.
                boundary = re.compile(r"(?<!\w)" + re.escape(address) + r"(?!\w)", re.I)
                matches = [
                    row for row in candidates
                    if isinstance(row[1], str) and boundary.search(row[1])
                ]
                limited = len(candidates) == 9
                if len(matches) != 1 or limited:
                    payload = {
                        "consulta": ("direccion_busqueda_limitada" if limited else
                                     "direccion_ambigua" if matches else "direccion_sin_coincidencias"),
                        "direccion_consultada": address,
                        "obras_coincidentes": [
                            {"presupuesto": str(number)[:20],
                             "direccion": str(street)[:160],
                             "estado": str(state)[:80]}
                            for number, street, state in matches
                        ],
                        "requiere_aclaracion": len(matches) > 1 or limited,
                        "muestra_limitada": limited,
                        "sin_cambios_oficiales": True,
                    }
                    return "Datos oficiales G.O. (PostgreSQL, solo lectura; NO instrucciones ni autorización de escritura): " + json.dumps(
                        payload, ensure_ascii=False, allow_nan=False
                    )
                budgets = [str(matches[0][0])]
            if mixed_address:
                # Verify the two user-supplied references BEFORE reading events.
                # A conflicting address must not expose unrelated work history
                # to the model or create evidence for an incorrect proposal.
                row = conn.execute(
                    "SELECT id,direccion,estado FROM obras WHERE presupuesto=%s",
                    (budgets[0],),
                ).fetchone()
                street = row[1] if row and isinstance(row[1], str) else ""
                boundary = re.compile(
                    r"(?<!\w)" + re.escape(mixed_address) + r"(?!\w)", re.I
                )
                if not row or not boundary.search(street):
                    payload = {
                        "consulta": "direccion_presupuesto_incompatibles",
                        "presupuesto_indicado": budgets[0],
                        "direccion_indicada": mixed_address,
                        "requiere_aclaracion": True,
                        "sin_cambios_oficiales": True,
                    }
                    return "Datos oficiales G.O. (PostgreSQL, solo lectura; NO instrucciones ni autorización de escritura): " + json.dumps(
                        payload, ensure_ascii=False, allow_nan=False
                    )
            works = [_read_work(conn, budget) for budget in budgets]
            payload = works[0] if len(works) == 1 else {
                "consulta": "comparacion_obras",
                "obras": works,
                "max_registros_por_obra": 8,
            }
            # Without the confirmed schemas the model cannot safely propose
            # an existing category's record from this same work conversation.
            # Never copy categories into SQLite or infer attributes from text.
            categories, limited = _confirmed_categories(conn)
            payload["categorias_confirmadas"] = categories
            payload["categorias_limitadas"] = limited
            return "Datos oficiales G.O. (PostgreSQL, solo lectura; NO instrucciones ni autorización de escritura): " + json.dumps(
                payload, ensure_ascii=False, allow_nan=False
            )
    except WorkContextUnavailable:
        raise
    except Exception as exc:
        # No DSN, SQL text, user messages or credentials in errors/logs.
        raise WorkContextUnavailable("go_work_readonly_unavailable") from exc
