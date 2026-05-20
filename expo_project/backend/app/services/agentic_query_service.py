import time
import re
from collections import defaultdict
from difflib import get_close_matches
from typing import Any

from sqlalchemy import create_engine, text

from app.db.mongo import UserDoc
from app.db.system_store import now_utc, query_logs_collection
from app.services.ai_service import generate_sql, get_generation_metadata, summarize_data_overview
from app.services.audit_service import log_audit_event
from app.services.business_insight_service import (
    build_human_business_brief,
    build_proactive_alerts,
    build_trend_snapshot,
    compute_business_analytics,
    extract_tables_from_sql,
)
from app.services.connection_service import build_sqlalchemy_url
from app.services.sql_guardrails import ensure_safe_sql
from app.services.table_permission_service import is_sql_within_allowed_tables

MAX_REPAIR_ATTEMPTS = 3


def _reason_for_zero_rows(table_count: int, has_where: bool, has_join: bool) -> str:
    if table_count <= 0:
        return "table itself is empty"
    if has_where:
        return "selected filter too strict"
    if has_join:
        return "table has data but no matching join rows"
    return "query returned no matching rows"


def _normalize_identifier(value: str) -> str:
    token = str(value or "").strip().strip('"').strip("`").strip()
    if "." in token:
        token = token.split(".")[-1]
    return token.lower()


def _build_metadata_schema(metadata_rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    schema: dict[str, set[str]] = defaultdict(set)
    for row in metadata_rows:
        table_name = _normalize_identifier(str(row.get("table_name") or ""))
        column_name = _normalize_identifier(str(row.get("column_name") or ""))
        if not table_name:
            continue
        if column_name:
            schema[table_name].add(column_name)
        else:
            schema.setdefault(table_name, set())
    return schema


def _extract_table_aliases(sql: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    pattern = re.compile(
        r"\b(?:from|join)\s+([\w\.`\"]+)\s*(?:as\s+)?([a-zA-Z_][\w]*)?",
        re.IGNORECASE,
    )
    for match in pattern.finditer(sql or ""):
        table_token = _normalize_identifier(match.group(1))
        alias_token = _normalize_identifier(match.group(2) or table_token)
        if table_token:
            aliases[alias_token] = table_token
            aliases[table_token] = table_token
    return aliases


def _validate_sql_schema(sql: str, metadata_rows: list[dict[str, Any]]) -> list[str]:
    schema = _build_metadata_schema(metadata_rows)
    if not schema:
        return []

    issues: list[str] = []
    known_tables = set(schema.keys())

    used_tables = {str(item or "").strip().lower() for item in extract_tables_from_sql(sql)}
    unknown_tables = sorted(table for table in used_tables if table and table not in known_tables)
    if unknown_tables:
        issues.append("unknown tables: " + ", ".join(unknown_tables))

    aliases = _extract_table_aliases(sql)
    col_ref_pattern = re.compile(r"\b([a-zA-Z_][\w]*)\s*\.\s*([a-zA-Z_][\w]*)\b")
    for alias, column in col_ref_pattern.findall(sql or ""):
        alias_key = _normalize_identifier(alias)
        col_key = _normalize_identifier(column)
        table_key = aliases.get(alias_key)
        if not table_key:
            continue
        table_columns = schema.get(table_key, set())
        if table_columns and col_key not in table_columns:
            issues.append(f"unknown column '{alias}.{column}' for table '{table_key}'")

    deduped: list[str] = []
    seen = set()
    for issue in issues:
        if issue not in seen:
            deduped.append(issue)
            seen.add(issue)
    return deduped


def _is_simple_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", str(value or "").strip()))


def _build_zero_row_diagnostic(sql: str, metadata_rows: list[dict[str, Any]], conn: Any) -> dict[str, Any]:
    schema = _build_metadata_schema(metadata_rows)
    known_tables = set(schema.keys())
    used_tables = [str(item or "").strip().lower() for item in extract_tables_from_sql(sql) if item]
    primary_table = next((table for table in used_tables if table in known_tables), "")
    has_join = bool(re.search(r"\bjoin\b", sql or "", flags=re.IGNORECASE))
    has_where = bool(re.search(r"\bwhere\b", sql or "", flags=re.IGNORECASE))

    table_count = -1
    count_error = ""
    if primary_table and _is_simple_identifier(primary_table):
        try:
            count_sql = f"SELECT COUNT(1) AS c FROM {primary_table}"
            table_count = int(conn.execute(text(count_sql)).scalar() or 0)
        except Exception as exc:
            count_error = str(exc)

    reason = _reason_for_zero_rows(table_count, has_where, has_join)
    return {
        "reason": reason,
        "primary_table": primary_table,
        "primary_table_count": table_count if table_count >= 0 else None,
        "has_join": has_join,
        "has_where": has_where,
        "probe_error": count_error or None,
    }


def _tokenize(text_value: str) -> set[str]:
    return {token for token in str(text_value or "").lower().replace("/", " ").replace("-", " ").split() if token}


def _expand_prompt_tokens(prompt_tokens: set[str], candidate_tokens: set[str]) -> set[str]:
    """Add fuzzy-matched tokens so minor spelling mistakes still map to known metadata."""
    expanded = set(prompt_tokens)
    if not candidate_tokens:
        return expanded
    candidates = sorted(candidate_tokens)
    for token in list(prompt_tokens):
        if len(token) < 3 or token in candidate_tokens:
            continue
        matches = get_close_matches(token, candidates, n=2, cutoff=0.78)
        expanded.update(matches)
    return expanded


def _table_index(metadata_rows: list[dict]) -> dict[str, dict]:
    table_map: dict[str, dict] = defaultdict(lambda: {"columns": [], "table_tokens": set(), "column_tokens": defaultdict(set)})
    for row in metadata_rows:
        table_name = str(row.get("table_name") or "").strip()
        column_name = str(row.get("column_name") or "").strip()
        if not table_name:
            continue
        entry = table_map[table_name]
        entry["table_tokens"].update(_tokenize(table_name))
        if column_name:
            entry["columns"].append(column_name)
            entry["column_tokens"][column_name].update(_tokenize(column_name))
    return table_map


def _score_table(prompt_tokens: set[str], table_name: str, table_entry: dict) -> int:
    score = 0
    score += len(prompt_tokens & table_entry["table_tokens"]) * 3
    for column_tokens in table_entry["column_tokens"].values():
        overlap = len(prompt_tokens & column_tokens)
        if overlap:
            score += overlap * 4
            if "name" in column_tokens:
                score += 1
            if "metric" in column_tokens or "amount" in column_tokens or "value" in column_tokens:
                score += 1
    lowered_table = table_name.lower()
    if lowered_table in prompt_tokens:
        score += 2
    return score


def _build_plan(prompt: str, connection: dict, metadata_rows: list[dict], allowed_tables: set[str], all_tables: bool) -> dict:
    prompt_tokens = _tokenize(prompt)
    table_map = _table_index(metadata_rows)

    candidate_tokens: set[str] = set()
    for item in table_map.values():
        candidate_tokens.update(item.get("table_tokens", set()))
        for col_tokens in item.get("column_tokens", {}).values():
            candidate_tokens.update(col_tokens)
    prompt_tokens = _expand_prompt_tokens(prompt_tokens, candidate_tokens)

    ranked_tables = sorted(
        (
            {
                "table_name": table_name,
                "score": _score_table(prompt_tokens, table_name, entry),
                "column_count": len(entry["columns"]),
                "sample_columns": entry["columns"][:5],
            }
            for table_name, entry in table_map.items()
        ),
        key=lambda item: (item["score"], item["column_count"], item["table_name"].lower()),
        reverse=True,
    )
    top_score = ranked_tables[0]["score"] if ranked_tables else 0
    second_score = ranked_tables[1]["score"] if len(ranked_tables) > 1 else 0
    confidence = "high" if top_score >= 6 and top_score > second_score else "medium" if top_score > 0 else "low"
    needs_clarification = not ranked_tables

    clarification_question = None
    if needs_clarification:
        clarification_question = "I can route this query, but I need a clearer business term, metric, or table name before execution."

    return {
        "connection_id": int(connection.get("connection_id", 0)),
        "connection_name": connection.get("name", ""),
        "db_type": connection.get("db_type", ""),
        "confidence": confidence,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "matched_tables": ranked_tables[:3],
        "auto_selected": bool(ranked_tables),
        "guardrails": {
            "read_only": True,
            "allowed_tables": [] if all_tables else sorted(allowed_tables),
        },
    }


def _build_insight_signals(rows: list[dict[str, Any]], analytics: dict) -> list[str]:
    signals: list[str] = []
    row_count = int(analytics.get("row_count", 0) or 0)
    numeric_columns = analytics.get("numeric_columns", {}) or {}
    null_counts = analytics.get("null_counts", {}) or {}

    if row_count == 0:
        return ["No rows returned for this query."]

    for column_name, stats in list(numeric_columns.items())[:3]:
        avg_value = float(stats.get("avg", 0) or 0)
        max_value = float(stats.get("max", 0) or 0)
        min_value = float(stats.get("min", 0) or 0)
        signals.append(f"{column_name}: avg {avg_value}, min {min_value}, max {max_value} across {stats.get('count', 0)} rows.")
        if avg_value > 0 and max_value >= avg_value * 3:
            signals.append(f"{column_name}: max is more than 3x the average, which can indicate a spike.")

    for column_name, null_count in list(null_counts.items())[:3]:
        if row_count and null_count:
            ratio = null_count / row_count
            if ratio >= 0.2:
                signals.append(f"{column_name}: {round(ratio * 100)}% null values, which is a completeness risk.")

    if not signals:
        signals.append(f"Returned {row_count} rows with no strong anomaly signals in the sampled output.")

    return signals[:5]


def _sql_references_metadata_table(sql: str, metadata_rows: list[dict]) -> bool:
    known_tables = {
        _normalize_identifier(str(item.get("table_name") or ""))
        for item in metadata_rows
        if _normalize_identifier(str(item.get("table_name") or ""))
    }
    if not known_tables:
        return False

    used_tables = {
        _normalize_identifier(str(table_name or ""))
        for table_name in extract_tables_from_sql(sql)
        if _normalize_identifier(str(table_name or ""))
    }
    return bool(used_tables.intersection(known_tables))


def _normalize_prompt_for_cache(prompt: str) -> str:
    return re.sub(r"\s+", " ", str(prompt or "").strip().lower())


def _find_reusable_cached_sql(
    user: UserDoc,
    prompt: str,
    connection: dict,
    metadata_rows: list[dict],
    *,
    all_tables: bool,
    allowed_tables: set[str],
) -> str | None:
    org = (user.organisation or "").strip().lower()
    connection_id = int(connection.get("connection_id", 0) or 0)
    normalized_prompt = _normalize_prompt_for_cache(prompt)
    if not org or not connection_id or not normalized_prompt:
        return None

    # Reuse the most recent SQL only when the same user asked the same prompt
    # for the same connection and the SQL is still safe under current metadata/permissions.
    docs = query_logs_collection().find(
        {
            "organisation": org,
            "employee_id": user.id,
            "agentic_trace.planner.connection_id": connection_id,
            "generated_sql": {"$exists": True, "$ne": ""},
        },
        {"generated_sql": 1, "user_prompt": 1, "created_at": 1},
    ).sort("created_at", -1).limit(20)

    for doc in docs:
        prior_prompt = _normalize_prompt_for_cache(str(doc.get("user_prompt") or ""))
        if prior_prompt != normalized_prompt:
            continue
        cached_sql = str(doc.get("generated_sql") or "").strip()
        if not cached_sql:
            continue
        try:
            ensure_safe_sql(cached_sql)
            if not _sql_references_metadata_table(cached_sql, metadata_rows):
                continue
            if not all_tables and not is_sql_within_allowed_tables(cached_sql, allowed_tables):
                continue
            if _validate_sql_schema(cached_sql, metadata_rows):
                continue
            return cached_sql
        except Exception:
            continue
    return None


def execute_agentic_sql_connection(
    user: UserDoc,
    prompt: str,
    connection: dict,
    metadata_rows: list[dict],
    *,
    all_tables: bool,
    allowed_tables: set[str],
    max_rows: int,
    repair_attempts: int = MAX_REPAIR_ATTEMPTS,
) -> dict:
    org = (user.organisation or "").strip().lower()
    plan = _build_plan(prompt, connection, metadata_rows, allowed_tables, all_tables)

    if plan.get("needs_clarification"):
        clarification_question = str(
            plan.get("clarification_question")
            or "Please clarify the metric, time range, or business entity before I run the query."
        )
        raise ValueError(f"Clarification required: {clarification_question}")

    generation_metadata = get_generation_metadata()
    attempts: list[dict[str, Any]] = []
    started = time.perf_counter()
    latest_error = ""
    generated_sql = ""
    rows: list[dict[str, Any]] = []
    zero_row_diagnostic: dict[str, Any] | None = None
    reused_cached_sql = False

    best_tables = [str(item.get("table_name") or "") for item in plan.get("matched_tables", []) if item.get("table_name")]
    prompt_for_sql = prompt
    if best_tables and all(table.lower() not in prompt.lower() for table in best_tables):
        prompt_for_sql = f"{prompt}\n\nPreferred table candidates: {', '.join(best_tables[:3])}."
    if not all_tables and allowed_tables:
        prompt_for_sql = f"{prompt_for_sql}\n\nAllowed tables only: {', '.join(sorted(allowed_tables))}."

    cached_sql = _find_reusable_cached_sql(
        user,
        prompt,
        connection,
        metadata_rows,
        all_tables=all_tables,
        allowed_tables=allowed_tables,
    )
    if cached_sql:
        try:
            generated_sql = cached_sql
            engine = create_engine(build_sqlalchemy_url(connection), pool_pre_ping=True)
            with engine.connect() as conn:
                result = conn.execute(text(generated_sql))
                rows = [dict(item) for item in result.mappings().fetchmany(max_rows)]
                if not rows:
                    zero_row_diagnostic = _build_zero_row_diagnostic(generated_sql, metadata_rows, conn)
            reused_cached_sql = True
        except Exception as exc:
            latest_error = str(exc)
            attempts.append(
                {
                    "attempt": 0,
                    "source": "cache",
                    "sql": generated_sql,
                    "error": f"cached sql execution failed: {latest_error}",
                }
            )
            generated_sql = ""

    if not reused_cached_sql:
        for attempt_index in range(max(1, repair_attempts)):
            repair_hint = latest_error if attempt_index > 0 else ""
            generated_sql = generate_sql(prompt_for_sql, metadata_rows, repair_hint=repair_hint)
            ensure_safe_sql(generated_sql)
            if not _sql_references_metadata_table(generated_sql, metadata_rows):
                latest_error = (
                    "Generated query must reference at least one table from assigned metadata. "
                    "Capability/help responses are not valid analytics SQL."
                )
                attempts.append({"attempt": attempt_index + 1, "source": "llm", "sql": generated_sql, "error": latest_error})
                if attempt_index + 1 >= max(1, repair_attempts):
                    raise ValueError(latest_error)
                continue
            if not all_tables and not is_sql_within_allowed_tables(generated_sql, allowed_tables):
                latest_error = (
                    "Generated query referenced tables outside permitted scope. "
                    f"Use only these tables: {', '.join(sorted(allowed_tables))}."
                )
                attempts.append({"attempt": attempt_index + 1, "source": "llm", "sql": generated_sql, "error": latest_error})
                if attempt_index + 1 >= max(1, repair_attempts):
                    raise ValueError(latest_error)
                continue

            schema_issues = _validate_sql_schema(generated_sql, metadata_rows)
            if schema_issues:
                latest_error = (
                    "Schema validation failed. Use only available metadata tables/columns. "
                    + "; ".join(schema_issues[:5])
                )
                attempts.append({"attempt": attempt_index + 1, "source": "llm", "sql": generated_sql, "error": latest_error})
                if attempt_index + 1 >= max(1, repair_attempts):
                    raise ValueError(latest_error)
                continue

            try:
                engine = create_engine(build_sqlalchemy_url(connection), pool_pre_ping=True)
                with engine.connect() as conn:
                    result = conn.execute(text(generated_sql))
                    rows = [dict(item) for item in result.mappings().fetchmany(max_rows)]
                    if not rows:
                        zero_row_diagnostic = _build_zero_row_diagnostic(generated_sql, metadata_rows, conn)
                break
            except Exception as exc:
                latest_error = str(exc)
                attempts.append({"attempt": attempt_index + 1, "source": "llm", "sql": generated_sql, "error": latest_error})
                if attempt_index + 1 >= max(1, repair_attempts):
                    raise ValueError(f"Query repair failed after {attempt_index + 1} attempts: {latest_error}") from exc

    execution_time = time.perf_counter() - started
    analytics = compute_business_analytics(rows)
    llm_overview = summarize_data_overview(prompt, rows, analytics)
    tables_in_scope = [str(item.get("table_name", "")) for item in plan.get("matched_tables", []) if item.get("table_name")]
    tables_used = extract_tables_from_sql(generated_sql)
    trend_snapshot = build_trend_snapshot(rows, analytics)
    proactive_alerts = build_proactive_alerts(analytics, trend_snapshot)
    overview = build_human_business_brief(
        prompt,
        [
            {
                "connection_id": int(connection.get("connection_id", 0)),
                "connection_name": connection.get("name", ""),
                "db_type": connection.get("db_type", ""),
                "query_language": "sql",
                "query_text": generated_sql,
            }
        ],
        analytics,
        proactive_alerts,
        trend_snapshot,
        tables_in_scope,
        tables_used,
    )
    insight_signals = _build_insight_signals(rows, analytics)
    if zero_row_diagnostic and not rows:
        insight_signals = [
            f"No rows returned because {zero_row_diagnostic.get('reason', 'query returned no matching rows')}."
        ]

    query_logs_collection().insert_one(
        {
            "organisation": org,
            "employee_id": user.id,
            "user_prompt": prompt,
            "generated_sql": generated_sql,
            "execution_time": execution_time,
            "agentic_trace": {
                "planner": plan,
                "sql_source": "cache" if reused_cached_sql else "llm",
                "repair_attempts": attempts,
                "insight_signals": insight_signals,
                "zero_row_diagnostic": zero_row_diagnostic,
                "proactive_alerts": proactive_alerts,
                "tables_used": tables_used,
                "tables_in_scope": tables_in_scope,
                "trend_snapshot": trend_snapshot,
            },
            "created_at": now_utc(),
        }
    )

    if attempts:
        log_audit_event(
            actor_user_id=user.id,
            actor_role=user.role,
            organisation=org,
            action="agentic.query.repair",
            target_type="connection",
            target_id=str(connection.get("connection_id", "")),
            details={"attempts": attempts, "selected_connection": plan.get("connection_name", "")},
        )

    log_audit_event(
        actor_user_id=user.id,
        actor_role=user.role,
        organisation=org,
        action="agentic.query.completed",
        target_type="connection",
        target_id=str(connection.get("connection_id", "")),
        details={
            "confidence": plan.get("confidence"),
            "repair_attempts": len(attempts),
            "row_count": len(rows),
            "db_type": connection.get("db_type", ""),
        },
    )

    return {
        "connection_id": int(connection.get("connection_id", 0)),
        "connection_name": connection.get("name", ""),
        "db_type": connection.get("db_type", ""),
        "generated_sql": generated_sql,
        "rows": rows,
        "columns": list(rows[0].keys()) if rows else [],
        "execution_time": execution_time,
        "overview": overview,
        "llm_overview": llm_overview,
        "analytics": analytics,
        "proactive_alerts": proactive_alerts,
        "trend_snapshot": trend_snapshot,
        "tables_used": tables_used,
        "tables_in_scope": tables_in_scope,
        "zero_row_diagnostic": zero_row_diagnostic,
        "generation": generation_metadata,
        "agentic": {
            "mode": "small-agent",
            "planner": plan,
            "policy": {
                "status": "approved",
                "max_rows": max_rows,
                "read_only": True,
            },
            "repair": {
                "status": "repaired" if attempts else "not-needed",
                "attempts": attempts,
                "max_attempts": repair_attempts,
            },
            "insight": {
                "summary": overview,
                "signals": insight_signals,
                "zero_row_diagnostic": zero_row_diagnostic,
                "proactive_alerts": proactive_alerts,
                "trend_snapshot": trend_snapshot,
                "tables_used": tables_used,
                "tables_in_scope": tables_in_scope,
            },
            "sql_source": "cache" if reused_cached_sql else "llm",
        },
    }
