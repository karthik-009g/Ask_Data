import json
import logging
import os
import re
from collections import defaultdict

from openai import OpenAI

from app.core.config import settings
from app.db.system_store import metadata_collection, permissions_collection


logger = logging.getLogger(__name__)


def _compact_llm_context(value, *, max_items: int = 8, max_depth: int = 3):
    if max_depth <= 0:
        return str(value)[:200]
    if isinstance(value, dict):
        compact = {}
        for idx, key in enumerate(value.keys()):
            if idx >= max_items:
                break
            compact[str(key)] = _compact_llm_context(value.get(key), max_items=max_items, max_depth=max_depth - 1)
        return compact
    if isinstance(value, list):
        return [
            _compact_llm_context(item, max_items=max_items, max_depth=max_depth - 1)
            for item in value[:max_items]
        ]
    text = str(value)
    return text if len(text) <= 200 else f"{text[:200]}..."


def _build_ai_client() -> tuple[OpenAI | None, str]:
    if settings.groq_api_key:
        return OpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1"), settings.groq_model
    if settings.openai_api_key:
        return OpenAI(api_key=settings.openai_api_key), settings.openai_model
    return None, ""


KEYWORD_GROUPS = {
    "student": {"student", "students", "roll", "rollno", "roll_no", "learner", "pupil"},
    "attendance": {"attendance", "attendence", "present", "presence", "absent", "absentees"},
    "name": {"name", "student_name", "full_name", "fullname"},
    "score": {"score", "marks", "mark", "grade", "gpa", "percent", "percentage"},
    "department": {"department", "dept", "branch", "program"},
}


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9_\s]", " ", (value or "").lower()).strip()


def _tokenize(value: str) -> set[str]:
    normalized = _normalize_text(value)
    parts = set(normalized.split())
    for token in list(parts):
        for canonical, aliases in KEYWORD_GROUPS.items():
            if token in aliases:
                parts.add(canonical)
    return {token for token in parts if token}


def _quote_identifier(identifier: str) -> str:
    safe = str(identifier or "").replace('"', '""')
    return f'"{safe}"'


def _build_table_index(metadata_rows: list[dict]) -> dict[str, dict]:
    table_map: dict[str, dict] = defaultdict(lambda: {"columns": [], "column_tokens": defaultdict(set), "table_tokens": set()})
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
    table_tokens = table_entry["table_tokens"]
    column_tokens = table_entry["column_tokens"]

    score += len(prompt_tokens & table_tokens) * 3
    for col, tokens in column_tokens.items():
        overlap = len(prompt_tokens & tokens)
        if overlap:
            score += overlap * 4
            if "name" in tokens:
                score += 1
            if "attendance" in tokens:
                score += 2
            if "student" in tokens:
                score += 2

    if "student" in prompt_tokens and "student" in table_tokens:
        score += 4
    if "attendance" in prompt_tokens and "attendance" in table_tokens:
        score += 4
    if "department" in prompt_tokens and "department" in table_tokens:
        score += 2
    if "attendance" in prompt_tokens and "department" in table_tokens:
        score -= 2
    if table_name.lower() in {"department", "departments"} and ("student" in prompt_tokens or "attendance" in prompt_tokens):
        score -= 4

    return score


def _pick_column(columns: list[str], preferred_tokens: set[str]) -> str | None:
    best_col = None
    best_score = -1
    for col in columns:
        col_tokens = _tokenize(col)
        score = len(col_tokens & preferred_tokens)
        if score > best_score:
            best_score = score
            best_col = col
    return best_col if best_score > 0 else None


def _build_fallback_sql(prompt: str, metadata_rows: list[dict]) -> str:
    table_map = _build_table_index(metadata_rows)
    if not table_map:
        return "SELECT 1"

    prompt_tokens = _tokenize(prompt)
    ranked = sorted(
        table_map.items(),
        key=lambda item: _score_table(prompt_tokens, item[0], item[1]),
        reverse=True,
    )
    table_name, table_entry = ranked[0]
    columns = table_entry["columns"]

    wants_top = any(token in prompt_tokens for token in {"top", "highest", "max", "most"})
    wants_low = any(token in prompt_tokens for token in {"lowest", "least", "less", "min"})
    wants_name = "name" in prompt_tokens
    wants_attendance = "attendance" in prompt_tokens

    limit = 100
    for token in prompt_tokens:
        if token.isdigit():
            numeric = int(token)
            if 1 <= numeric <= 500:
                limit = numeric
                break

    if wants_attendance:
        attendance_col = _pick_column(columns, {"attendance", "present", "presence", "absent"})
        name_col = _pick_column(columns, {"name", "student", "full", "first", "last"})
        if attendance_col and name_col:
            direction = "ASC" if wants_low else "DESC" if wants_top else "ASC"
            return (
                f"SELECT {_quote_identifier(name_col)}, {_quote_identifier(attendance_col)} "
                f"FROM {_quote_identifier(table_name)} "
                f"ORDER BY {_quote_identifier(attendance_col)} {direction} "
                f"LIMIT {limit}"
            )
        if attendance_col:
            direction = "ASC" if wants_low else "DESC" if wants_top else "ASC"
            return (
                f"SELECT * FROM {_quote_identifier(table_name)} "
                f"ORDER BY {_quote_identifier(attendance_col)} {direction} "
                f"LIMIT {limit}"
            )

    if wants_name:
        name_col = _pick_column(columns, {"name", "student", "full", "first", "last"})
        if name_col:
            return f"SELECT {_quote_identifier(name_col)} FROM {_quote_identifier(table_name)} LIMIT {limit}"

    return f"SELECT * FROM {_quote_identifier(table_name)} LIMIT {limit}"


def get_generation_metadata() -> dict:
    if settings.groq_api_key:
        return {"mode": "llm", "provider": "groq", "model": settings.groq_model}
    if settings.openai_api_key:
        return {"mode": "llm", "provider": "openai", "model": settings.openai_model}
    return {"mode": "fallback", "provider": "none", "model": "heuristic"}


def _parse_analytics_classifier_payload(content: str) -> dict | None:
    text = str(content or "").strip()
    if not text:
        return None

    # 1) Strict JSON body.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 2) JSON embedded in markdown/code-fences or surrounding prose.
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # 3) Soft parse from text labels when provider does not obey strict JSON.
    lowered = text.lower()
    if "non-analytics" in lowered or "not analytics" in lowered:
        return {"is_analytics": False, "intent": "non-analytics", "reason": "classified from text output"}
    if "analytics" in lowered and "non-analytics" not in lowered and "not analytics" not in lowered:
        return {"is_analytics": True, "intent": "analytics", "reason": "classified from text output"}
    return None


def classify_prompt_for_analytics(prompt: str) -> dict:
    text = str(prompt or "").strip()
    if not text:
        return {
            "is_analytics": False,
            "intent": "non-analytics",
            "reason": "empty prompt",
            "provider": "system",
            "model": "none",
        }

    client, model_name = _build_ai_client()
    if not client or not model_name:
        return {
            "is_analytics": False,
            "intent": "non-analytics",
            "reason": "llm unavailable",
            "provider": "system",
            "model": "none",
        }

    system = (
        "You are an intent classifier for an analytics SQL assistant. "
        "Task: decide whether the prompt asks to execute real data analysis/SQL, or only asks for guidance/help/examples. "
        "Return ONLY valid JSON with keys: is_analytics (boolean), intent (analytics|non-analytics), reason (short string). "
        "Classification rules:\n"
        "- analytics: asks to retrieve/aggregate/filter/compare real dataset rows or metrics.\n"
        "- non-analytics: greetings, capability questions, chit-chat, and requests to generate examples/prompts/questions/queries.\n"
        "- If user asks to 'generate natural queries/questions/prompts' (even mentioning table names), classify non-analytics.\n"
        "Examples:\n"
        "1) Prompt: 'show top 10 customers by revenue last month' => {\"is_analytics\": true, \"intent\": \"analytics\", \"reason\": \"asks for metric retrieval\"}\n"
        "2) Prompt: 'you can read these tables; help me generate simple queries in natural language' => {\"is_analytics\": false, \"intent\": \"non-analytics\", \"reason\": \"asks for example queries, not execution\"}\n"
        "3) Prompt: 'generate the natural queries on attendance table' => {\"is_analytics\": false, \"intent\": \"non-analytics\", \"reason\": \"request is for query ideas/examples\"}"
    )
    user = f"Classify this prompt:\n{text}"

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            max_tokens=140,
        )
        content = str(response.choices[0].message.content or "").strip()
        payload = _parse_analytics_classifier_payload(content)
        if not payload:
            raise ValueError("Classifier returned unparsable output")
        is_analytics = bool(payload.get("is_analytics", False))
        intent = "analytics" if is_analytics else "non-analytics"
        return {
            "is_analytics": is_analytics,
            "intent": intent,
            "reason": str(payload.get("reason") or "classified by llm").strip()[:200],
            "provider": "groq" if settings.groq_api_key else "openai",
            "model": model_name,
        }
    except Exception as exc:
        logger.warning("LLM intent classification failed, defaulting to non-analytics: %s", exc)
        return {
            "is_analytics": False,
            "intent": "non-analytics",
            "reason": "llm classification failed",
            "provider": "system",
            "model": "none",
        }


def choose_connection_id(employee_id: str, prompt: str) -> int | None:
    permissions = list(
        permissions_collection().find(
            {"employee_id": employee_id, "can_query": True},
            {"connection_id": 1},
        )
    )
    if not permissions:
        return None

    allowed_connection_ids = [int(item["connection_id"]) for item in permissions]
    metadata = list(
        metadata_collection().find(
            {"connection_id": {"$in": allowed_connection_ids}},
            {"connection_id": 1, "table_name": 1, "column_name": 1, "data_type": 1},
        )
    )

    prompt_lower = prompt.lower()
    score: dict[int, int] = {connection_id: 0 for connection_id in allowed_connection_ids}
    for row in metadata:
        table_name = str(row.get("table_name", "")).lower()
        column_name = str(row.get("column_name", "")).lower()
        data_type = str(row.get("data_type", "")).lower()

        if table_name and table_name in prompt_lower:
            score[int(row["connection_id"])] += 2
        if column_name and column_name in prompt_lower:
            score[int(row["connection_id"])] += 2
        if data_type and data_type in prompt_lower:
            score[int(row["connection_id"])] += 1

    best = sorted(score.items(), key=lambda item: item[1], reverse=True)
    if best and best[0][1] > 0:
        return best[0][0]
    return allowed_connection_ids[0]


def generate_sql(prompt: str, metadata_rows: list[dict], repair_hint: str | None = None) -> str:
    ordered_metadata_rows = sorted(
        metadata_rows,
        key=lambda m: (
            str(m.get("table_name") or "").lower(),
            str(m.get("column_name") or "").lower(),
            str(m.get("data_type") or "").lower(),
        ),
    )
    metadata_text = "\n".join(
        [
            f"table={m.get('table_name')}, column={m.get('column_name')}, type={m.get('data_type')}"
            for m in ordered_metadata_rows[:300]
        ]
    )
    repair_text = f"\n\nRepair notes: {repair_hint}" if repair_hint else ""

    client, model_name = _build_ai_client()
    if client:
        system = (
            "You are a SQL assistant. Generate a single safe SELECT query only. "
            "Never generate DROP, DELETE, UPDATE, INSERT, TRUNCATE, ALTER, CREATE, or grant/revoke statements. "
            "If repair notes are present, fix the prior SQL issue while staying read only."
        )
        user = f"Metadata:\n{metadata_text}\n\nPrompt: {prompt}{repair_text}\nReturn SQL only."
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0,
            )
            return response.choices[0].message.content.strip().strip("`")
        except Exception as exc:
            logger.warning("LLM SQL generation failed; falling back to heuristic SQL: %s", exc)

    fallback_prompt = prompt if not repair_hint else f"{prompt}\n\nRepair notes: {repair_hint}"
    return _build_fallback_sql(fallback_prompt, metadata_rows)


def summarize_data_overview(prompt: str, rows: list[dict], analytics: dict) -> str:
    if not rows:
        return "No rows were returned, so there is no analytical summary available."

    sample_rows = rows[:20]
    client, model_name = _build_ai_client()
    if client:
        system = "You are a data analyst. Provide a concise business overview with key insights from query output."
        user = (
            f"Prompt: {prompt}\n"
            f"Rows sample: {json.dumps(sample_rows, default=str)}\n"
            f"Analytics: {json.dumps(analytics, default=str)}\n"
            "Return 3-6 short bullet-style insights in plain text."
        )
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            pass

    numeric_columns = analytics.get("numeric_columns", {})
    pieces = [f"Returned {len(rows)} rows."]
    for column_name, stats in list(numeric_columns.items())[:3]:
        pieces.append(
            f"{column_name}: avg={stats.get('avg')}, min={stats.get('min')}, max={stats.get('max')}."
        )
    return " ".join(pieces)


def generate_system_assistant_response(
    user_query: str,
    user_role: str,
    user_org: str,
    intent: str,
    entities: dict,
    operation_result: dict,
    last_response: dict | None = None,
    metadata_context: dict | None = None,
) -> str | None:
    """
    Generate final natural-language answer for system assistant from the operation output.
    Falls back to deterministic router message if LLM is unavailable.
    """
    # Keep test runs deterministic and offline-safe.
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None

    client, model_name = _build_ai_client()
    if not client or not model_name:
        return None

    result_copy = {
        "response_type": operation_result.get("response_type"),
        "message": operation_result.get("message"),
        "data": operation_result.get("data") or {},
        "next_steps": operation_result.get("next_steps") or [],
    }

    # Keep prompt size bounded while preserving most useful metadata.
    if isinstance(result_copy["data"], dict):
        data_obj = dict(result_copy["data"])
        for key in ("connections", "tables", "columns", "employees", "logs"):
            value = data_obj.get(key)
            if isinstance(value, list) and len(value) > 30:
                data_obj[key] = value[:30]
        result_copy["data"] = data_obj

    prior_summary = {
        "type": (last_response or {}).get("type"),
        "message": (last_response or {}).get("message"),
        "next_steps": (last_response or {}).get("next_steps") or [],
    }
    metadata_summary = _compact_llm_context(metadata_context or {}, max_items=10, max_depth=2)
    entity_summary = _compact_llm_context(entities or {}, max_items=10, max_depth=2)

    def _compose_user_payload(include_metadata: bool) -> str:
        parts = [
            f"user_query: {user_query}",
            f"user_role: {user_role}",
            f"user_org: {user_org}",
            f"intent: {intent}",
            f"entities: {json.dumps(entity_summary, default=str)}",
            f"operation_result: {json.dumps(result_copy, default=str)}",
            f"last_response: {json.dumps(prior_summary, default=str)}",
        ]
        if include_metadata:
            parts.insert(5, f"metadata_context: {json.dumps(metadata_summary, default=str)}")
        return "\n".join(parts) + "\n\nReturn only one plain-text assistant message."

    system = (
        "You are the Enterprise System Assistant. "
        "Generate the final answer ONLY from provided operation result and context. "
        "Do not invent data, IDs, tables, or permissions. "
        "Never provide SQL queries or analytics output. "
        "Never reveal sensitive data such as passwords, tokens, raw connection URLs, encrypted fields, or secrets. "
        "If the operation_result has list data, include key names clearly. "
        "Keep answer concise, practical, and role-aware. "
        "Limit output to at most 200 tokens."
    )
    for include_metadata in (True, False):
        try:
            user = _compose_user_payload(include_metadata=include_metadata)
            call_variants = [
                {
                    "temperature": 0,
                    "max_tokens": 200,
                },
                {
                    "temperature": 0,
                },
            ]
            for extra_args in call_variants:
                try:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                        **extra_args,
                    )
                    text = (response.choices[0].message.content or "").strip()
                    if text:
                        return text
                except Exception as variant_exc:
                    logger.warning(
                        "System assistant LLM variant failed (include_metadata=%s, args=%s): %s",
                        include_metadata,
                        extra_args,
                        variant_exc,
                    )
        except Exception as exc:
            logger.warning(
                "System assistant LLM response generation failed (include_metadata=%s): %s",
                include_metadata,
                exc,
            )
    return None
