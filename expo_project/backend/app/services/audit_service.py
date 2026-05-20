from typing import Any

from app.db.system_store import audit_logs_collection, now_utc


def log_audit_event(
    *,
    actor_user_id: str,
    actor_role: str,
    organisation: str,
    action: str,
    target_type: str,
    target_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    audit_logs_collection().insert_one(
        {
            "actor_user_id": actor_user_id,
            "actor_role": actor_role,
            "organisation": (organisation or "").strip().lower(),
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "details": details or {},
            "created_at": now_utc(),
        }
    )
