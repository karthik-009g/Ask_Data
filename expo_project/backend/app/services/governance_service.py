from datetime import datetime, timezone

from app.db.system_store import audit_logs_collection, governance_limits_collection, query_logs_collection, now_utc

DEFAULT_GOVERNANCE_LIMITS = {
    "max_queries_per_employee_per_day": 200,
    "max_exports_per_employee_per_day": 30,
    "max_rows_per_query": 500,
}


def get_org_governance_limits(organisation: str) -> dict:
    org = (organisation or "").strip().lower()
    if not org:
        return DEFAULT_GOVERNANCE_LIMITS.copy()

    coll = governance_limits_collection()
    row = coll.find_one({"organisation": org})
    if not row:
        coll.insert_one({"organisation": org, **DEFAULT_GOVERNANCE_LIMITS, "updated_at": now_utc()})
        return DEFAULT_GOVERNANCE_LIMITS.copy()

    return {
        "max_queries_per_employee_per_day": int(row.get("max_queries_per_employee_per_day", DEFAULT_GOVERNANCE_LIMITS["max_queries_per_employee_per_day"])),
        "max_exports_per_employee_per_day": int(row.get("max_exports_per_employee_per_day", DEFAULT_GOVERNANCE_LIMITS["max_exports_per_employee_per_day"])),
        "max_rows_per_query": int(row.get("max_rows_per_query", DEFAULT_GOVERNANCE_LIMITS["max_rows_per_query"])),
    }


def upsert_org_governance_limits(organisation: str, payload: dict) -> dict:
    org = (organisation or "").strip().lower()
    if not org:
        raise ValueError("Organisation is required")

    values = {
        "max_queries_per_employee_per_day": int(payload.get("max_queries_per_employee_per_day", DEFAULT_GOVERNANCE_LIMITS["max_queries_per_employee_per_day"])),
        "max_exports_per_employee_per_day": int(payload.get("max_exports_per_employee_per_day", DEFAULT_GOVERNANCE_LIMITS["max_exports_per_employee_per_day"])),
        "max_rows_per_query": int(payload.get("max_rows_per_query", DEFAULT_GOVERNANCE_LIMITS["max_rows_per_query"])),
    }

    for key, value in values.items():
        if value < 1:
            raise ValueError(f"{key} must be at least 1")

    governance_limits_collection().update_one(
        {"organisation": org},
        {"$set": {**values, "updated_at": now_utc()}},
        upsert=True,
    )
    return values


def _today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


def count_employee_queries_today(employee_id: str) -> int:
    return query_logs_collection().count_documents(
        {
            "employee_id": employee_id,
            "created_at": {"$gte": _today_start()},
        }
    )


def count_employee_exports_today(employee_id: str, organisation: str) -> int:
    org = (organisation or "").strip().lower()
    return audit_logs_collection().count_documents(
        {
            "organisation": org,
            "actor_user_id": employee_id,
            "action": {"$in": ["employee.export", "employee.analyse.export"]},
            "created_at": {"$gte": _today_start()},
        }
    )
