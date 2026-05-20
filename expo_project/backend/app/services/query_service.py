import re

from app.db.mongo import UserDoc
from app.db.system_store import connections_collection, metadata_collection, permissions_collection
from app.services.agentic_query_service import execute_agentic_sql_connection
from app.services.governance_service import get_org_governance_limits
from app.services.prompt_intent_service import try_build_direct_answer
from app.services.table_permission_service import normalize_allowed_tables, normalize_table_name

MAX_METADATA_ROWS_PER_CONNECTION = 5000


def execute_prompt(employee: UserDoc, prompt: str) -> tuple[str, list[dict], float]:
    direct = try_build_direct_answer(employee, prompt)
    if direct:
        return "", direct.get("rows", []), 0.0

    employee_id_str = employee.id
    org = (employee.organisation or "").strip().lower()
    if not org:
        raise ValueError("Employee organisation is missing")
    org_filter = {"organisation": {"$regex": f"^{re.escape(org)}$", "$options": "i"}}

    org_connection_ids = {
        int(item["connection_id"])
        for item in connections_collection().find(org_filter, {"connection_id": 1})
    }
    query_allowed_ids = {
        int(item["connection_id"])
        for item in permissions_collection().find(
            {
                "employee_id": employee_id_str,
                "organisation": {"$regex": f"^{re.escape(org)}$", "$options": "i"},
                "can_query": True,
            },
            {"connection_id": 1},
        )
    }
    allowed_connection_ids = sorted(org_connection_ids.intersection(query_allowed_ids))
    if not allowed_connection_ids:
        raise ValueError("No permitted database available")

    sql_candidates = list(
        connections_collection().find(
            {
                **org_filter,
                "connection_id": {"$in": allowed_connection_ids},
                "db_type": {"$in": ["mysql", "postgresql"]},
            }
        )
    )
    if not sql_candidates:
        raise ValueError("No SQL database available for this prompt")

    best_score = -1
    selected_connection = None
    selected_allowed_tables: set[str] = set()
    selected_all_tables = True
    prompt_lower = prompt.lower()
    for candidate in sql_candidates:
        candidate_id = int(candidate["connection_id"])
        permission_doc = permissions_collection().find_one(
            {
                "employee_id": employee_id_str,
                "organisation": {"$regex": f"^{re.escape(org)}$", "$options": "i"},
                "connection_id": candidate_id,
                "can_query": True,
            },
            {"allowed_tables": 1},
        )
        if not permission_doc:
            continue
        all_tables, allowed_set = normalize_allowed_tables((permission_doc or {}).get("allowed_tables", ["*"]))
        rows = list(
            metadata_collection().find(
                {"connection_id": candidate_id},
                {"table_name": 1, "column_name": 1, "data_type": 1},
            ).limit(MAX_METADATA_ROWS_PER_CONNECTION)
        )
        if not all_tables:
            rows = [
                row
                for row in rows
                if normalize_table_name(str(row.get("table_name", ""))) in allowed_set
            ]
            if not rows:
                continue

        score = 0
        for row in rows:
            table_name = str(row.get("table_name", "")).lower()
            column_name = str(row.get("column_name", "")).lower()
            data_type = str(row.get("data_type", "")).lower()
            if table_name and table_name in prompt_lower:
                score += 2
            if column_name and column_name in prompt_lower:
                score += 2
            if data_type and data_type in prompt_lower:
                score += 1
        if score > best_score:
            best_score = score
            selected_connection = candidate
            selected_allowed_tables = allowed_set
            selected_all_tables = all_tables

    if not selected_connection:
        raise ValueError("No permitted database available")

    connection_id = int(selected_connection["connection_id"])
    metadata_rows = list(
        metadata_collection().find({"connection_id": connection_id}).limit(MAX_METADATA_ROWS_PER_CONNECTION)
    )
    if not selected_all_tables:
        metadata_rows = [
            row
            for row in metadata_rows
            if normalize_table_name(str(row.get("table_name", ""))) in selected_allowed_tables
        ]
        if not metadata_rows:
            raise ValueError("No permitted tables available for selected connection")

    limits = get_org_governance_limits(org)
    max_rows = int(limits.get("max_rows_per_query", 500))
    result = execute_agentic_sql_connection(
        employee,
        prompt,
        selected_connection,
        metadata_rows,
        all_tables=selected_all_tables,
        allowed_tables=selected_allowed_tables,
        max_rows=max_rows,
    )

    return result["generated_sql"], result["rows"], result["execution_time"]
