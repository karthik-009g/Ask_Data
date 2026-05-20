import re

UNSAFE_PATTERN = re.compile(
    r"\b(drop|delete|truncate|alter|update|insert|create|grant|revoke|merge|replace|call|exec|execute|upsert|lock|begin|commit|rollback|for\s+update)\b",
    re.IGNORECASE,
)
READ_ONLY_MESSAGE = "Only read only is allowed"


def ensure_safe_sql(sql: str) -> None:
    cleaned_sql = (sql or "").strip()
    if not cleaned_sql:
        raise ValueError(READ_ONLY_MESSAGE)

    statements = [part.strip() for part in cleaned_sql.split(";") if part.strip()]
    if len(statements) != 1:
        raise ValueError(READ_ONLY_MESSAGE)

    statement = statements[0].lower()
    if not (statement.startswith("select") or statement.startswith("with")):
        raise ValueError(READ_ONLY_MESSAGE)

    if UNSAFE_PATTERN.search(statement):
        raise ValueError(READ_ONLY_MESSAGE)
