import re
import json
import os
from typing import Any

from openai import OpenAI

from app.core.config import settings

DATA_QUERY_INTENT = "DATA_QUERY"
LIST_TABLES_INTENT = "list_tables"
DESCRIBE_TABLE_INTENT = "describe_table"
LIST_COLUMNS_INTENT = "list_columns"
GREETING_INTENT = "greeting"
SMALL_TALK_INTENT = "small_talk"
HELP_GENERAL_INTENT = "help_general"
CAPABILITY_QUERY_INTENT = "capability_query"
ORG_INFO_INTENT = "org_info"
CLARIFICATION_NEEDED_INTENT = "clarification_needed"
FOLLOW_UP_INTENT = "follow_up"
SECURITY_BLOCKED_INTENT = "security_blocked"

ADMIN_INTENTS = {
    "admin_list_employees",
    "admin_create_employee",
    "admin_delete_employee",
    "admin_list_connections",
    "admin_create_connection",
    "admin_update_connection",
    "admin_delete_connection",
    "admin_assign_permission",
    "admin_view_metadata",
    "admin_view_logs",
    "admin_view_access",
    "employee_request_access",
    LIST_TABLES_INTENT,
    DESCRIBE_TABLE_INTENT,
    LIST_COLUMNS_INTENT,
    GREETING_INTENT,
    SMALL_TALK_INTENT,
    HELP_GENERAL_INTENT,
    CAPABILITY_QUERY_INTENT,
    ORG_INFO_INTENT,
    CLARIFICATION_NEEDED_INTENT,
    FOLLOW_UP_INTENT,
    SECURITY_BLOCKED_INTENT,
}

EMPLOYEE_INTENTS = {
    "employee_list_connections",
    "employee_view_schema",
    "employee_permission_issue",
    "employee_request_access",
    "employee_help",
    "employee_export_request",
    LIST_TABLES_INTENT,
    DESCRIBE_TABLE_INTENT,
    LIST_COLUMNS_INTENT,
    GREETING_INTENT,
    SMALL_TALK_INTENT,
    HELP_GENERAL_INTENT,
    CAPABILITY_QUERY_INTENT,
    ORG_INFO_INTENT,
    CLARIFICATION_NEEDED_INTENT,
    FOLLOW_UP_INTENT,
    SECURITY_BLOCKED_INTENT,
}


_DATA_KEYWORDS = {
    "sales",
    "revenue",
    "profit",
    "users",
    "top",
    "average",
    "trend",
    "count",
    "sum",
    "avg",
    "monthly",
    "growth",
    "last week",
}

_DATA_PATTERNS = [
    re.compile(r"\b(last\s+month|last\s+week|weekly\s+trend|month\s+over\s+month)\b", re.IGNORECASE),
    re.compile(r"\b(total|how\s+many|highest|lowest|min|max)\b", re.IGNORECASE),
]

_GREETINGS = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}
_SMALL_TALK = {"how are you", "what's up", "whats up", "how r u"}
_HELP_TERMS = {"help", "help me", "what can you do", "how to use this", "what can i ask", "guide me", "help me use this system"}
_CAPABILITY_TERMS = {"can you explain tables", "can you show schema", "what is this system", "explain this system", "explain schema"}
_ORG_INFO_TERMS = {
    "what is my organisation",
    "what is my organization",
    "my organisation",
    "my organization",
    "which organisation",
    "which organization",
    "what org am i in",
    "what organization am i in",
}
_FOLLOW_UP_TERMS = {"explain more", "what next", "next", "then what"}
_VAGUE_TERMS = {"show something", "give info", "do analysis"}
_SECURITY_PATTERNS = [
    re.compile(r"\b(drop\s+database|delete\s+all\s+employees|truncate|union\s+select|bypass\s+permissions?)\b", re.IGNORECASE),
    re.compile(r"\b(give\s+me\s+admin\s+access|ignore\s+rules)\b", re.IGNORECASE),
]

_LLM_AVAILABLE_INTENTS = [
    "greeting",
    "help",
    "admin_list_employees",
    "list_connections",
    "list_tables",
    "describe_table",
    "employee_permission_issue",
    "export_request",
    "DATA_QUERY",
]


def _build_ai_client() -> tuple[OpenAI | None, str]:
    if settings.groq_api_key:
        return OpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1"), settings.groq_model
    if settings.openai_api_key:
        return OpenAI(api_key=settings.openai_api_key), settings.openai_model
    return None, ""


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None


def _merge_llm_entities(target: dict[str, Any], llm_entities: dict[str, Any]) -> None:
    if not isinstance(llm_entities, dict):
        return

    for key in [
        "email",
        "employee_id",
        "connection_id",
        "previous_context_id",
        "table_name",
        "database_name",
        "export_format",
        "db_type",
        "full_name",
    ]:
        value = llm_entities.get(key)
        if value is None:
            continue
        if key in {"connection_id"}:
            try:
                value = int(value)
            except Exception:
                continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        if not target.get(key):
            target[key] = value


def _map_llm_intent_to_internal(raw_intent: str, role: str) -> str | None:
    intent = (raw_intent or "").strip()
    mapping = {
        "greeting": GREETING_INTENT,
        "help": HELP_GENERAL_INTENT,
        "admin_list_employees": "admin_list_employees",
        "list_tables": LIST_TABLES_INTENT,
        "describe_table": DESCRIBE_TABLE_INTENT,
        "employee_permission_issue": "employee_permission_issue",
        "export_request": "employee_export_request",
        "DATA_QUERY": DATA_QUERY_INTENT,
    }

    if intent == "list_connections":
        return "admin_list_connections" if role == "admin" else "employee_list_connections"

    return mapping.get(intent)


def _llm_classify_and_extract(user_query: str, user_role: str, metadata_context: dict[str, Any] | None = None) -> tuple[str | None, dict[str, Any]]:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None, {}

    client, model_name = _build_ai_client()
    if not client or not model_name:
        return None, {}

    prompt = (
        "You are an intent classifier.\n\n"
        "Given a user query, return:\n"
        "- intent (from available list)\n"
        "- extracted entities\n\n"
        "Rules:\n"
        "- If query is about data analysis -> return DATA_QUERY\n"
        "- If query is about employees -> admin_list_employees\n"
        "- If query is about databases -> list_connections\n"
        "- If query is about tables -> list_tables\n"
        "- If query is about columns/schema -> describe_table\n"
        "- Do not invent fields not present in query/context.\n"
        "- Never include secrets, passwords, tokens, or credentials in entities.\n\n"
        "Return JSON ONLY:\n"
        "{\n"
        '  "intent": "",\n'
        '  "entities": {}\n'
        "}\n"
    )
    payload = {
        "query": user_query,
        "available_intents": _LLM_AVAILABLE_INTENTS,
        "role": user_role,
        "metadata_context": metadata_context or {},
    }

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, default=str)},
            ],
            temperature=0,
        )
        content = (response.choices[0].message.content or "").strip()
        parsed = _extract_json_object(content)
        if not parsed:
            return None, {}

        raw_intent = str(parsed.get("intent") or "").strip()
        entities = parsed.get("entities") if isinstance(parsed.get("entities"), dict) else {}
        internal_intent = _map_llm_intent_to_internal(raw_intent=raw_intent, role=(user_role or "").strip().lower())
        return internal_intent, entities
    except Exception:
        return None, {}


def _heuristic_fallback_classifier(user_query: str, user_role: str) -> tuple[str | None, dict[str, Any]]:
    return _legacy_rule_classifier(user_query=user_query, user_role=user_role), {}


def _legacy_rule_classifier(user_query: str, user_role: str) -> str:
    normalized = _normalize(user_query)
    role = (user_role or "").strip().lower()

    if any(pattern.search(normalized) for pattern in _SECURITY_PATTERNS):
        return SECURITY_BLOCKED_INTENT
    if normalized in _GREETINGS:
        return GREETING_INTENT
    if normalized in _SMALL_TALK:
        return SMALL_TALK_INTENT
    if any(token in normalized for token in {"organization", "organisation", "org"}) and any(token in normalized for token in {"my", "what", "which"}):
        return ORG_INFO_INTENT
    if detect_data_query(normalized):
        return DATA_QUERY_INTENT

    if any(token in normalized for token in {"log", "logs", "audit", "recent activity", "failed queries"}):
        return "admin_view_logs"

    if any(token in normalized for token in {"metadata", "schema"}) and role == "admin":
        return "admin_view_metadata"

    if any(token in normalized for token in {"permission", "permissions", "access"}) and (
        any(token in normalized for token in {"assign", "grant", "set", "update", "give", "remove", "revoke", "bypass"})
        or "who has access" in normalized
    ):
        if "who has access" in normalized:
            return "admin_view_access"
        return "admin_assign_permission"

    if any(token in normalized for token in {"add", "create", "invite", "new"}) and any(token in normalized for token in {"employee", "employees"}):
        return "admin_create_employee"
    if any(token in normalized for token in {"delete", "remove"}) and any(token in normalized for token in {"employee", "employees"}):
        return "admin_delete_employee"

    if any(token in normalized for token in {"columns", "column", "fields", "field"}):
        return LIST_COLUMNS_INTENT
    if any(token in normalized for token in {"describe", "structure"}) and "table" in normalized:
        return DESCRIBE_TABLE_INTENT
    if "schema" in normalized and role == "employee":
        return "employee_view_schema"
    if any(token in normalized for token in {"permission", "access denied", "forbidden"}) or ((("can't" in normalized) or ("cannot" in normalized)) and "access" in normalized):
        if "request access" in normalized:
            return "employee_request_access"
        return "employee_permission_issue"

    if "request access" in normalized:
        return "employee_request_access"

    if any(token in normalized for token in {"employee", "employees"}):
        return "admin_list_employees"
    if "connection" in normalized and any(token in normalized for token in {"add", "create", "new"}):
        return "admin_create_connection"
    if "connection" in normalized and any(token in normalized for token in {"update", "edit", "change"}):
        return "admin_update_connection"
    if "connection" in normalized and any(token in normalized for token in {"delete", "remove"}):
        return "admin_delete_connection"

    if any(token in normalized for token in {"table", "tables"}):
        return LIST_TABLES_INTENT

    if any(token in normalized for token in {"database", "databases", "connection", "connections", "db", "data source", "data sources", "source", "sources"}):
        if role == "admin":
            return "admin_list_connections"
        if any(token in normalized for token in {"list", "show", "my", "assigned", "have", "access", "data source", "sources", "given", "what", "which"}):
            return "employee_list_connections"
        return "employee_permission_issue"

    if any(token in normalized for token in {"column", "columns", "structure", "describe"}):
        return DESCRIBE_TABLE_INTENT
    if any(token in normalized for token in {"export", "download", "csv", "excel", "pdf"}):
        return ("employee_export_request" if role == "employee" else HELP_GENERAL_INTENT)
    if any(token in normalized for token in {"help", "guide", "how to", "what can you do", "example", "examples"}):
        return HELP_GENERAL_INTENT

    if normalized in _VAGUE_TERMS:
        return CLARIFICATION_NEEDED_INTENT

    return "employee_help" if role == "employee" else "admin_view_metadata"


def _normalize(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    typo_fixes = [
        (r"\bwhata\s+re\b", "what are"),
        (r"\bwhata\b", "what"),
        (r"\bdata\s+bases\b", "databases"),
        (r"\bemployyes\b", "employees"),
        (r"\bemployes\b", "employees"),
        (r"\bemplyees\b", "employees"),
    ]
    for pattern, replacement in typo_fixes:
        normalized = re.sub(pattern, replacement, normalized)
    return normalized


def _contains_any(text: str, words: set[str]) -> bool:
    return any(word in text for word in words)


def _has_employee_word(text: str) -> bool:
    if any(token in text for token in {"employee", "employees"}):
        return True
    return re.search(r"\bemploy\w*\b", text) is not None


def _has_database_word(text: str) -> bool:
    return any(
        token in text
        for token in {
            "connection",
            "connections",
            "database",
            "databases",
            "data base",
            "db",
            "data source",
            "data sources",
            "source",
            "sources",
        }
    )


def _is_database_listing_query(text: str, role: str) -> bool:
    if not _has_database_word(text):
        return False

    explicit_listing_terms = {
        "list",
        "show",
        "all",
        "have",
        "my",
        "assigned",
        "access",
        "given",
    }
    if any(token in text for token in explicit_listing_terms):
        return True

    # Handle natural question formats like "what are the databases".
    if any(token in text for token in {"what", "which"}) and "database" in text:
        if role == "admin":
            return True
        if role == "employee":
            return any(token in text for token in {"me", "my", "i", "to me"}) or "what are the databases" in text

    return False


def detect_data_query(user_query: str) -> bool:
    normalized = _normalize(user_query)
    if _contains_any(normalized, _DATA_KEYWORDS):
        return True
    return any(pattern.search(normalized) for pattern in _DATA_PATTERNS)


def is_table_query(query: str) -> bool:
    text = _normalize(query)
    keywords = {"table", "tables"}
    actions = {"show", "list", "what", "name", "give", "which", "exist", "there"}
    has_keywords = any(keyword in text for keyword in keywords)
    has_actions = any(action in text for action in actions)
    if has_keywords and has_actions:
        return True
    if has_keywords and (text.startswith("tables ") or "tables in " in text):
        return True
    return False


def is_describe_table_query(query: str) -> bool:
    text = _normalize(query)
    return (
        ("describe" in text and "table" in text)
        or text.startswith("describe ")
        or ("structure" in text and "table" in text)
    )


def is_columns_query(query: str) -> bool:
    text = _normalize(query)
    return any(token in text for token in {"column", "columns", "field", "fields"}) and any(
        token in text for token in {"in", "of", "show", "what", "which", "list"}
    )


def classify_intent(user_query: str, user_role: str, entities: dict[str, Any]) -> str:
    role = (user_role or "").strip().lower()
    metadata_context = entities.get("_llm_metadata") if isinstance(entities.get("_llm_metadata"), dict) else None

    if os.getenv("PYTEST_CURRENT_TEST"):
        entities["_intent_source"] = "heuristic-fallback"
        return _legacy_rule_classifier(user_query=user_query, user_role=role)

    inferred_intent, llm_entities = _llm_classify_and_extract(
        user_query=user_query,
        user_role=role,
        metadata_context=metadata_context,
    )

    if inferred_intent:
        _merge_llm_entities(entities, llm_entities)
        try:
            validate_role(intent=inferred_intent, user_role=role)
            entities["_intent_source"] = "llm"
            return inferred_intent
        except PermissionError:
            pass

    fallback_intent, fallback_entities = _heuristic_fallback_classifier(user_query=user_query, user_role=role)
    if fallback_intent:
        _merge_llm_entities(entities, fallback_entities)
        entities["_intent_source"] = "heuristic-fallback"
        return fallback_intent

    entities["_intent_source"] = "default"
    return "employee_help" if role == "employee" else "admin_view_metadata"


def _llm_fallback_intent(user_query: str, user_role: str, entities: dict[str, Any]) -> str | None:
    role = (user_role or "").strip().lower()
    metadata_context = entities.get("_llm_metadata") if isinstance(entities.get("_llm_metadata"), dict) else None
    inferred_intent, llm_entities = _llm_classify_and_extract(user_query=user_query, user_role=role, metadata_context=metadata_context)
    if not inferred_intent:
        return None

    _merge_llm_entities(entities, llm_entities)

    # Validate role permissions before returning LLM-selected intent.
    try:
        validate_role(intent=inferred_intent, user_role=role)
    except PermissionError:
        return None

    entities["_intent_source"] = "llm"
    return inferred_intent


def validate_role(intent: str, user_role: str) -> None:
    role = (user_role or "").strip().lower()
    if intent == DATA_QUERY_INTENT:
        return
    if role == "admin" and intent in ADMIN_INTENTS:
        return
    if role == "employee" and intent in EMPLOYEE_INTENTS:
        return
    raise PermissionError("Intent is not allowed for this role")
