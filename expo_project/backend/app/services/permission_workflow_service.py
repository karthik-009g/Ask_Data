from app.db.system_store import permissions_collection
from app.services.table_permission_service import normalize_allowed_tables


def apply_employee_permissions(organisation: str, employee_id: str, permissions: list[dict]) -> int:
    org = (organisation or "").strip().lower()
    coll = permissions_collection()

    coll.delete_many({"employee_id": employee_id})
    docs = []
    for entry in permissions:
        if not entry.get("can_read"):
            continue
        all_tables, allowed_set = normalize_allowed_tables(entry.get("allowed_tables"))
        allowed_tables = ["*"] if all_tables else sorted(allowed_set)
        docs.append(
            {
                "organisation": org,
                "employee_id": employee_id,
                "connection_id": int(entry["connection_id"]),
                "can_read": bool(entry.get("can_read", False)),
                "can_query": bool(entry.get("can_query", False)),
                "can_visualize": bool(entry.get("can_visualize", False)),
                "can_export": bool(entry.get("can_export", False)),
                "allowed_tables": allowed_tables,
            }
        )

    if docs:
        coll.insert_many(docs)
    return len(docs)
