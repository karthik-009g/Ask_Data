import re
from typing import Any

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_OBJECT_ID_RE = re.compile(r"\b[a-fA-F0-9]{24}\b")
_CONNECTION_ID_RE = re.compile(r"\b(?:connection(?:\s*id)?|conn(?:ection)?\s*id|id)\s*[:#-]?\s*(\d+)\b", re.IGNORECASE)
_RESULT_CONTEXT_RE = re.compile(r"\b(?:result|context)(?:_id|\s*id)?\s*[:=#-]?\s*([A-Za-z0-9_-]{4,128})\b", re.IGNORECASE)
_DESCRIBE_TABLE_RE = re.compile(r"\bdescribe\s+(?:table\s+)?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_TABLE_SUFFIX_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s+table\b", re.IGNORECASE)
_COLUMNS_IN_RE = re.compile(r"\b(?:columns?|fields?)\s+(?:are\s+in|in|of)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_DATABASE_RE = re.compile(r"\bin\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:database|db)\b", re.IGNORECASE)
_TABLE_PLACEHOLDER_WORDS = {"table", "tables", "particular", "perticular", "specific", "this", "that", "the", "a", "an"}


def extract_entities(user_query: str) -> dict[str, Any]:
    text = (user_query or "").strip()
    lower = text.lower()

    email_match = _EMAIL_RE.search(text)
    object_id_match = _OBJECT_ID_RE.search(text)
    connection_match = _CONNECTION_ID_RE.search(text)
    context_match = _RESULT_CONTEXT_RE.search(text)
    table_name = _extract_table_name(text)
    database_match = _DATABASE_RE.search(text)

    export_format = _extract_export_format(lower)
    db_type = _extract_db_type(lower)
    permissions = _extract_permission_flags(lower)

    return {
        "email": email_match.group(0).lower() if email_match else None,
        "employee_id": object_id_match.group(0) if object_id_match else None,
        "connection_id": int(connection_match.group(1)) if connection_match else None,
        "previous_context_id": context_match.group(1) if context_match else None,
        "table_name": table_name,
        "database_name": database_match.group(1).lower() if database_match else None,
        "export_format": export_format,
        "db_type": db_type,
        "permissions": permissions,
        "full_name": _extract_name_before_email(text, email_match.start() if email_match else None),
        "connection_payload": _extract_connection_payload(text),
    }


def _extract_export_format(lower: str) -> str | None:
    if "csv" in lower:
        return "csv"
    if "excel" in lower or "xlsx" in lower:
        return "excel"
    if "pdf" in lower:
        return "pdf"
    return None


def _extract_db_type(lower: str) -> str | None:
    if "postgres" in lower or "postgresql" in lower:
        return "postgresql"
    if "mysql" in lower:
        return "mysql"
    if "mongodb" in lower or "mongo" in lower:
        return "mongodb"
    return None


def _extract_permission_flags(lower: str) -> dict[str, bool]:
    # Defaults keep behavior explicit and secure.
    can_read = "read" in lower or "view" in lower
    can_query = "query" in lower or "sql" in lower
    can_visualize = "visual" in lower or "chart" in lower
    can_export = "export" in lower or "download" in lower

    if any(flag is True for flag in (can_read, can_query, can_visualize, can_export)):
        return {
            "can_read": can_read,
            "can_query": can_query,
            "can_visualize": can_visualize,
            "can_export": can_export,
        }

    return {
        "can_read": True,
        "can_query": False,
        "can_visualize": False,
        "can_export": False,
    }


def _extract_name_before_email(text: str, email_start: int | None) -> str | None:
    if email_start is None:
        return None
    prefix = text[:email_start].strip(" ,:-")
    if not prefix:
        return None

    cleaned = re.sub(r"\b(add|create|invite|employee|new)\b", "", prefix, flags=re.IGNORECASE).strip(" ,:-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned if cleaned else None


def _extract_table_name(text: str) -> str | None:
    for pattern in (_COLUMNS_IN_RE, _DESCRIBE_TABLE_RE, _TABLE_SUFFIX_RE):
        match = pattern.search(text)
        if match:
            candidate = match.group(1).strip().lower()
            if candidate in _TABLE_PLACEHOLDER_WORDS:
                return None
            return candidate
    return None


def _extract_connection_payload(text: str) -> dict[str, Any]:
    # Supports command-like text, e.g. "name=sales db_type=postgresql host=..."
    payload: dict[str, Any] = {}
    for key in ["name", "db_type", "host", "port", "username", "password", "database_name", "connection_url", "method"]:
        pattern = re.compile(rf"\b{key}\s*=\s*([^\s,;]+)", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            value = match.group(1).strip().strip('"\'')
            payload[key] = value

    if "port" in payload:
        try:
            payload["port"] = int(payload["port"])
        except Exception:
            payload.pop("port", None)

    if payload and "method" not in payload:
        payload["method"] = "url" if payload.get("connection_url") else "form"

    return payload
