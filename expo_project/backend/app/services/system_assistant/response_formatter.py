from typing import Any

ALLOWED_TYPES = {"action", "info", "error", "redirect"}


def format_response(
    response_type: str,
    message: str,
    data: dict[str, Any] | None = None,
    next_steps: list[str] | None = None,
) -> dict[str, Any]:
    normalized_type = response_type if response_type in ALLOWED_TYPES else "error"
    return {
        "type": normalized_type,
        "message": (message or "").strip() or "No message",
        "data": data or {},
        "next_steps": next_steps or [],
    }


def redirect_to_sql_bot() -> dict[str, Any]:
    return format_response(
        response_type="redirect",
        message="This request requires data analysis. Forwarding to query assistant.",
        data={"target": "SQL_BOT"},
        next_steps=["Open the SQL assistant tab and run this question there."],
    )
