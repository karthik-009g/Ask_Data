import re
from typing import Iterable

_TABLE_PATTERN = re.compile(r"\b(?:from|join)\s+([`\"\[\]\w\.]+)", re.IGNORECASE)


def normalize_table_name(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    text = text.strip("`\"[]")
    if "." in text:
        text = text.split(".")[-1]
    return text.strip().lower()


def normalize_allowed_tables(values: Iterable[str] | None) -> tuple[bool, set[str]]:
    if not values:
        return True, set()

    normalized: set[str] = set()
    for item in values:
        token = (item or "").strip()
        if not token:
            continue
        if token == "*":
            return True, set()
        normalized_name = normalize_table_name(token)
        if normalized_name:
            normalized.add(normalized_name)

    if not normalized:
        return True, set()
    return False, normalized


def extract_sql_table_names(sql: str) -> set[str]:
    query = sql or ""
    names: set[str] = set()
    for match in _TABLE_PATTERN.findall(query):
        normalized = normalize_table_name(match)
        if normalized:
            names.add(normalized)
    return names


def is_sql_within_allowed_tables(sql: str, allowed_tables: set[str]) -> bool:
    if not allowed_tables:
        return True

    referenced = extract_sql_table_names(sql)
    if not referenced:
        return True

    return referenced.issubset(allowed_tables)
