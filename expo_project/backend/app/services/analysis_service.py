import json
import re
import time
from collections import defaultdict
from difflib import get_close_matches
from typing import Any

from bson import ObjectId
from pymongo import MongoClient
from sqlalchemy import create_engine, text

from app.db.mongo import UserDoc, get_users_collection
from app.db.system_store import (
    connections_collection,
    metadata_collection,
    permissions_collection,
    query_logs_collection,
    now_utc,
)
from app.services.agentic_query_service import execute_agentic_sql_connection
from app.services.ai_service import summarize_data_overview, get_generation_metadata, classify_prompt_for_analytics
from app.services.business_insight_service import (
    build_human_business_brief,
    build_proactive_alerts,
    build_trend_snapshot,
    compute_business_analytics,
    extract_tables_from_sql,
)
from app.services.connection_service import build_mongo_uri, resolve_mongo_database
from app.services.governance_service import get_org_governance_limits
from app.services.prompt_intent_service import try_build_direct_answer
from app.services.table_permission_service import normalize_allowed_tables, normalize_table_name

MAX_METADATA_ROWS_PER_CONNECTION = 5000


def _is_table_inventory_prompt(prompt: str) -> bool:
    text = (prompt or "").strip().lower()
    if not text:
        return False
    asks_for_tables = bool(re.search(r"\btables?\b", text))
    access_context = any(token in text for token in ["assigned", "for me", "access", "permission", "available", "which tables"])
    return asks_for_tables and access_context


def _is_column_inventory_prompt(prompt: str) -> bool:
    text = (prompt or "").strip().lower()
    if not text:
        return False
    asks_for_columns = any(token in text for token in ["columns", "fields", "schema", "attributes"])
    context = any(token in text for token in ["table", "dataset", "db", "database", "relation"])
    return asks_for_columns and context


def _extract_target_table_name(prompt: str) -> str | None:
    text = (prompt or "").strip().lower()
    if not text:
        return None

    patterns = [
        r"(?:columns|fields|schema)\s+(?:in|of|for)\s+(?:the\s+)?([a-zA-Z0-9_\.]+)\s+table",
        r"([a-zA-Z0-9_\.]+)\s+table\s+(?:columns|fields|schema)",
        r"table\s+([a-zA-Z0-9_\.]+)\s+(?:columns|fields|schema)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return normalize_table_name(match.group(1))
    return None


def _build_table_inventory_rows(connection_id: int, connection_name: str, metadata_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique_table_names = sorted(
        {
            str(item.get("table_name") or "").strip()
            for item in metadata_rows
            if str(item.get("table_name") or "").strip()
        }
    )
    return [
        {
            "connection_id": connection_id,
            "connection_name": connection_name,
            "table_name": table_name,
            "access": "assigned",
        }
        for table_name in unique_table_names
    ]


def _build_column_inventory_rows(
    connection_id: int,
    connection_name: str,
    metadata_rows: list[dict[str, Any]],
    target_table: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in metadata_rows:
        table_name = normalize_table_name(str(item.get("table_name") or ""))
        if not table_name:
            continue
        if target_table and table_name != target_table:
            continue
        rows.append(
            {
                "connection_id": connection_id,
                "connection_name": connection_name,
                "table_name": table_name,
                "column_name": str(item.get("column_name") or "").strip(),
                "data_type": str(item.get("data_type") or "").strip(),
                "access": "assigned",
            }
        )
    rows.sort(key=lambda item: (item["table_name"], item["column_name"]))
    return rows


def _allowed_connection_ids(user: UserDoc, is_admin: bool) -> list[int]:
    org = _resolve_user_organisation(user)
    if not org:
        return []

    org_filter = {"organisation": {"$regex": f"^{re.escape(org)}$", "$options": "i"}}

    if is_admin:
        return [
            int(item["connection_id"])
            for item in connections_collection().find(org_filter, {"connection_id": 1})
        ]

    org_connection_ids = {
        int(item["connection_id"])
        for item in connections_collection().find(org_filter, {"connection_id": 1})
    }
    permitted_ids = {
        int(item["connection_id"])
        for item in permissions_collection().find(
            {
                "employee_id": user.id,
                "organisation": {"$regex": f"^{re.escape(org)}$", "$options": "i"},
                "can_query": True,
            },
            {"connection_id": 1},
        )
    }
    return sorted(org_connection_ids.intersection(permitted_ids))


def _readable_connection_ids(user: UserDoc, is_admin: bool) -> list[int]:
    org = _resolve_user_organisation(user)
    if not org:
        return []

    org_filter = {"organisation": {"$regex": f"^{re.escape(org)}$", "$options": "i"}}

    if is_admin:
        return [
            int(item["connection_id"])
            for item in connections_collection().find(org_filter, {"connection_id": 1})
        ]

    org_connection_ids = {
        int(item["connection_id"])
        for item in connections_collection().find(org_filter, {"connection_id": 1})
    }
    readable_ids = {
        int(item["connection_id"])
        for item in permissions_collection().find(
            {
                "employee_id": user.id,
                "organisation": {"$regex": f"^{re.escape(org)}$", "$options": "i"},
                "$or": [
                    {"can_read": True},
                    {"can_query": True},
                    {"can_visualize": True},
                    {"can_export": True},
                ],
            },
            {"connection_id": 1},
        )
    }
    return sorted(org_connection_ids.intersection(readable_ids))


def _resolve_user_organisation(user: UserDoc) -> str:
    org = (user.organisation or "").strip()
    if org:
        return org
    try:
        doc = get_users_collection().find_one({"_id": ObjectId(user.id)}, {"organisation": 1})
        return str((doc or {}).get("organisation") or "").strip()
    except Exception:
        return ""


def _tokenize_prompt(text_value: str) -> set[str]:
    return {token for token in re.sub(r"[^a-z0-9_\s]", " ", str(text_value or "").lower()).split() if token}


def _expand_tokens(tokens: set[str], vocabulary: set[str]) -> set[str]:
    expanded = set(tokens)
    if not vocabulary:
        return expanded
    sorted_vocab = sorted(vocabulary)
    for token in list(tokens):
        if len(token) < 3 or token in vocabulary:
            continue
        expanded.update(get_close_matches(token, sorted_vocab, n=2, cutoff=0.78))
    return expanded


def _score_connection(prompt: str, metadata_rows: list[dict[str, Any]]) -> int:
    base_tokens = _tokenize_prompt(prompt)
    vocab: set[str] = set()
    for row in metadata_rows:
        vocab.update(_tokenize_prompt(str(row.get("table_name") or "")))
        vocab.update(_tokenize_prompt(str(row.get("column_name") or "")))
    prompt_tokens = _expand_tokens(base_tokens, vocab)

    score = 0
    for row in metadata_rows:
        table_tokens = _tokenize_prompt(str(row.get("table_name") or ""))
        column_tokens = _tokenize_prompt(str(row.get("column_name") or ""))
        score += len(prompt_tokens & table_tokens) * 3
        score += len(prompt_tokens & column_tokens) * 4
    return score


def _pick_best_connection_ids(prompt: str, candidate_ids: list[int]) -> list[int]:
    if len(candidate_ids) <= 1:
        return candidate_ids

    rows = list(
        metadata_collection().find(
            {"connection_id": {"$in": candidate_ids}},
            {"connection_id": 1, "table_name": 1, "column_name": 1},
        )
    )
    metadata_by_connection: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        metadata_by_connection[int(row.get("connection_id", 0))].append(row)

    table_names = {
        normalize_table_name(str(row.get("table_name") or ""))
        for row in rows
        if normalize_table_name(str(row.get("table_name") or ""))
    }
    lowered_prompt = (prompt or "").lower()
    mentions_known_table = any(table in lowered_prompt for table in table_names)
    if mentions_known_table:
        return candidate_ids

    scored = []
    for connection_id in candidate_ids:
        metadata_rows = metadata_by_connection.get(connection_id, [])
        score = _score_connection(prompt, metadata_rows)
        scored.append((connection_id, score, len(metadata_rows)))
    scored.sort(key=lambda item: (item[1], item[2]), reverse=True)

    if not scored:
        return candidate_ids[:1]
    return [scored[0][0]]


def _pick_mongo_collection(prompt: str, metadata_rows: list[dict[str, Any]]) -> str | None:
    tables = sorted({item.get("table_name") for item in metadata_rows if item.get("table_name")})
    if not tables:
        return None
    lowered = prompt.lower()
    for table in tables:
        if str(table).lower() in lowered:
            return str(table)
    return str(tables[0])


def _is_analytics_convertible_prompt(prompt: str) -> bool:
    result = classify_prompt_for_analytics(prompt)
    return bool(result.get("is_analytics", False))


def _build_non_analytics_response(message: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    analytics = compute_business_analytics(rows)
    trend_snapshot = {"has_time_series": False, "time_column": None, "weekly_changes": []}
    return {
        "generated_queries": [],
        "generated_sql": "",
        "rows": rows,
        "columns": [],
        "execution_time": 0.0,
        "overview": message,
        "llm_overview": message,
        "business_brief": message,
        "analytics": analytics,
        "proactive_alerts": [],
        "trend_snapshot": trend_snapshot,
        "tables_used": [],
        "tables_in_scope": [],
        "clarification_questions": [message],
        "zero_row_diagnostics": [],
        "zero_row_reason": "",
        "generation": {"mode": "intent-filter", "provider": "system", "model": "heuristic"},
        "agentic": {
            "mode": "intent-filter",
            "summary": {
                "selected_connections": 0,
                "sql_connections": 0,
                "mongodb_connections": 0,
                "row_count": 0,
            },
            "connections": [],
            "proactive_alerts": [],
            "trend_snapshot": trend_snapshot,
            "tables_used": [],
            "tables_in_scope": [],
            "clarification_questions": [message],
            "zero_row_diagnostics": [],
            "intent": {
                "name": "non-analytics",
                "no_sql_required": True,
            },
        },
    }


def _is_admin_employee_directory_prompt(prompt: str) -> bool:
    text = (prompt or "").strip().lower()
    if not text:
        return False
    asks_people = any(token in text for token in ["employee", "employees", "staff", "team", "employee name", "employee names"])
    asks_org = any(token in text for token in ["organisation", "organization", "company", "my org", "my organisation", "my organization"]) 
    asks_access = any(token in text for token in ["access", "permission", "permissions", "rights"])
    asks_dept = any(token in text for token in ["department", "departments", "dept"])
    return asks_people and (asks_org or asks_access or asks_dept)


def _build_admin_employee_directory_rows(organisation: str) -> list[dict[str, Any]]:
    if not str(organisation or "").strip():
        return []
    org_pattern = {"$regex": f"^{re.escape(str(organisation).strip())}$", "$options": "i"}
    docs = list(
        get_users_collection().find(
            {"organisation": org_pattern, "role": "employee"},
            {
                "full_name": 1,
                "position": 1,
                "department": 1,
                "location": 1,
                "manager_name": 1,
                "preferred_language": 1,
            },
        )
    )
    rows: list[dict[str, Any]] = []
    for item in docs:
        rows.append(
            {
                "employee_id": str(item.get("_id")),
                "full_name": str(item.get("full_name") or "").strip(),
                "position": str(item.get("position") or "").strip(),
                "department": str(item.get("department") or "").strip(),
                "location": str(item.get("location") or "").strip(),
                "manager_name": str(item.get("manager_name") or "").strip(),
                "preferred_language": str(item.get("preferred_language") or "").strip(),
            }
        )
    return rows


def _sanitize_mongo_doc(doc: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in doc.items():
        if isinstance(value, (dict, list)):
            sanitized[key] = json.loads(json.dumps(value, default=str))
        else:
            sanitized[key] = value if isinstance(value, (int, float, str, bool)) or value is None else str(value)
    return sanitized


def _build_safe_admin_employee_context(organisation: str) -> dict[str, Any]:
    users_coll = get_users_collection()
    org_pattern = {"$regex": f"^{re.escape(str(organisation or '').strip())}$", "$options": "i"}
    employee_docs = list(
        users_coll.find(
            {"organisation": org_pattern, "role": "employee"},
            {
                "full_name": 1,
                "position": 1,
                "department": 1,
                "location": 1,
                "manager_name": 1,
                "preferred_language": 1,
            },
        )
    )

    safe_employees: list[dict[str, Any]] = []
    employee_name_by_id: dict[str, str] = {}
    for doc in employee_docs:
        employee_id = str(doc.get("_id"))
        full_name = str(doc.get("full_name") or "").strip()
        employee_name_by_id[employee_id] = full_name
        safe_employees.append(
            {
                "employee_id": employee_id,
                "full_name": full_name,
                "position": str(doc.get("position") or "").strip(),
                "department": str(doc.get("department") or "").strip(),
                "location": str(doc.get("location") or "").strip(),
                "manager_name": str(doc.get("manager_name") or "").strip(),
                "preferred_language": str(doc.get("preferred_language") or "").strip(),
            }
        )

    org_connections = list(
        connections_collection().find(
            {"organisation": org_pattern},
            {"connection_id": 1, "name": 1},
        )
    )
    connection_name_by_id = {
        int(item.get("connection_id", 0)): str(item.get("name") or "")
        for item in org_connections
        if item.get("connection_id") is not None
    }

    permission_docs = list(
        permissions_collection().find(
            {"employee_id": {"$in": list(employee_name_by_id.keys())}},
            {
                "employee_id": 1,
                "connection_id": 1,
                "can_read": 1,
                "can_query": 1,
                "can_visualize": 1,
                "can_export": 1,
                "allowed_tables": 1,
            },
        )
    )

    permissions_by_employee: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for permission in permission_docs:
        employee_id = str(permission.get("employee_id") or "")
        connection_id = int(permission.get("connection_id", 0) or 0)
        all_tables, allowed_set = normalize_allowed_tables(permission.get("allowed_tables", ["*"]))
        permissions_by_employee[employee_id].append(
            {
                "connection_id": connection_id,
                "connection_name": connection_name_by_id.get(connection_id, f"connection-{connection_id}"),
                "can_read": bool(permission.get("can_read", False)),
                "can_query": bool(permission.get("can_query", False)),
                "can_visualize": bool(permission.get("can_visualize", False)),
                "can_export": bool(permission.get("can_export", False)),
                "table_scope": "all" if all_tables else f"selected:{len(allowed_set)}",
            }
        )

    employee_access_summary: list[dict[str, Any]] = []
    for employee in safe_employees:
        employee_id = employee.get("employee_id", "")
        employee_permissions = permissions_by_employee.get(str(employee_id), [])
        employee_access_summary.append(
            {
                "employee_id": employee_id,
                "full_name": employee.get("full_name", ""),
                "connection_count": len(employee_permissions),
                "permissions": employee_permissions[:20],
            }
        )

    return {
        "employee_count": len(safe_employees),
        "employees": safe_employees[:100],
        "employee_access_summary": employee_access_summary[:100],
    }


def _build_safe_super_admin_org_context() -> dict[str, Any]:
    users_coll = get_users_collection()

    organisation_rows = list(
        users_coll.aggregate(
            [
                {"$match": {"role": {"$in": ["admin", "employee"]}}},
                {
                    "$group": {
                        "_id": {"$ifNull": ["$organisation", ""]},
                        "employee_count": {"$sum": {"$cond": [{"$eq": ["$role", "employee"]}, 1, 0]}},
                        "admin_count": {"$sum": {"$cond": [{"$eq": ["$role", "admin"]}, 1, 0]}},
                    }
                },
                {"$sort": {"_id": 1}},
            ]
        )
    )

    connection_rows = list(
        connections_collection().aggregate(
            [
                {
                    "$group": {
                        "_id": {"$ifNull": ["$organisation", ""]},
                        "database_count": {"$sum": 1},
                    }
                }
            ]
        )
    )
    connection_map = {
        str(item.get("_id") or "").strip().lower(): int(item.get("database_count", 0))
        for item in connection_rows
    }

    organisations: list[dict[str, Any]] = []
    for item in organisation_rows:
        org = str(item.get("_id") or "").strip().lower()
        if not org:
            continue
        organisations.append(
            {
                "organisation": org,
                "admin_count": int(item.get("admin_count", 0)),
                "employee_count": int(item.get("employee_count", 0)),
                "database_count": connection_map.get(org, 0),
            }
        )

    known_orgs = {item["organisation"] for item in organisations}
    for org, database_count in connection_map.items():
        if org and org not in known_orgs:
            organisations.append(
                {
                    "organisation": org,
                    "admin_count": 0,
                    "employee_count": 0,
                    "database_count": int(database_count),
                }
            )

    organisations.sort(key=lambda item: item["organisation"])
    return {
        "organisation_count": len(organisations),
        "organisations": organisations[:200],
    }


def _try_admin_employee_chat_answer(prompt: str, user_context: dict[str, Any], data_context: dict[str, Any]) -> str | None:
    role = str(user_context.get("role") or "").strip().lower()
    if role != "admin":
        return None

    question = (prompt or "").strip().lower()
    asks_employee = any(
        token in question
        for token in [
            "employee",
            "employees",
            "employe",
            "emloyee",
            "emplyee",
            "staff",
            "team",
            "employee name",
            "employee names",
        ]
    )
    if not asks_employee:
        return None

    employee_directory = data_context.get("employee_directory") or {}
    employee_rows = employee_directory.get("employees") or []
    access_rows = employee_directory.get("employee_access_summary") or []
    if not employee_rows:
        return "No employee records are currently available for your organisation."

    asks_department = any(token in question for token in ["department", "departments", "dept", "deparment", "deparmnt"])
    asks_access = any(token in question for token in ["access", "permission", "permissions", "rights"])

    if asks_department:
        preview = ", ".join(
            f"{item.get('full_name')} ({item.get('department') or 'N/A'})"
            for item in employee_rows[:30]
            if item.get("full_name")
        )
        count = int(employee_directory.get("employee_count") or len(employee_rows))
        more = "" if count <= 30 else f" ... and {count - 30} more"
        if preview:
            return f"Employee names with departments: {preview}{more}."

    if asks_access and access_rows:
        matched = None
        for item in access_rows:
            full_name = str(item.get("full_name") or "").strip()
            if full_name and full_name.lower() in question:
                matched = item
                break
        if matched:
            permissions = matched.get("permissions") or []
            if not permissions:
                return f"{matched.get('full_name', 'Employee')} currently has no connection access assigned."
            snippets = []
            for permission in permissions[:8]:
                snippets.append(
                    f"{permission.get('connection_name')}: read={permission.get('can_read')}, query={permission.get('can_query')}, "
                    f"visualize={permission.get('can_visualize')}, export={permission.get('can_export')}, tables={permission.get('table_scope')}"
                )
            return f"Access summary for {matched.get('full_name')}: " + "; ".join(snippets) + "."

    names = ", ".join(str(item.get("full_name") or "").strip() for item in employee_rows[:20] if str(item.get("full_name") or "").strip())
    count = int(employee_directory.get("employee_count") or len(employee_rows))
    if names:
        more = "" if count <= 20 else f" ... and {count - 20} more"
        return f"Your organisation currently has {count} employees. Sample names: {names}{more}."
    return "No employee records are currently available for your organisation."


def execute_connection_analysis(
    user: UserDoc,
    prompt: str,
    connection_ids: list[int],
    is_admin: bool,
    mode: str = "analytics",
    max_rows_per_connection: int = 500,
) -> dict:
    normalized_mode = (mode or "analytics").strip().lower()
    org_name = _resolve_user_organisation(user)
    org_filter = {"organisation": {"$regex": f"^{re.escape(org_name)}$", "$options": "i"}} if org_name else {}

    if is_admin and _is_admin_employee_directory_prompt(prompt):
        safe_rows = _build_admin_employee_directory_rows(user.organisation or "")
        answer = (
            f"Found {len(safe_rows)} employees in your organisation."
            if safe_rows
            else "No employee records are currently available for your organisation."
        )
        analytics = compute_business_analytics(safe_rows)
        return {
            "generated_queries": [],
            "generated_sql": "",
            "rows": safe_rows,
            "columns": list(safe_rows[0].keys()) if safe_rows else [],
            "execution_time": 0.0,
            "overview": answer,
            "llm_overview": answer,
            "analytics": analytics,
            "proactive_alerts": build_proactive_alerts(analytics, {"has_time_series": False, "time_column": None, "weekly_changes": []}),
            "trend_snapshot": {"has_time_series": False, "time_column": None, "weekly_changes": []},
            "tables_used": ["system.users"],
            "tables_in_scope": ["system.users"],
            "clarification_questions": [],
            "generation": {"mode": "admin-directory", "provider": "system", "model": "deterministic"},
            "agentic": {
                "mode": "admin-directory",
                "summary": {
                    "selected_connections": 0,
                    "sql_connections": 0,
                    "mongodb_connections": 0,
                    "row_count": len(safe_rows),
                },
                "connections": [],
                "proactive_alerts": [],
                "trend_snapshot": {"has_time_series": False, "time_column": None, "weekly_changes": []},
                "tables_used": ["system.users"],
                "tables_in_scope": ["system.users"],
                "clarification_questions": [],
                "intent": {
                    "name": "admin.employee-directory",
                    "no_sql_required": True,
                },
            },
        }

    if normalized_mode == "chatbot":
        raise ValueError("Unsupported analysis mode")

    direct = try_build_direct_answer(user, prompt)
    if direct:
        rows = list(direct.get("rows", []))
        analytics = compute_business_analytics(rows)
        answer_text = str(direct.get("answer", "Answer generated from your profile context."))
        return {
            "generated_queries": [],
            "generated_sql": "",
            "rows": rows,
            "columns": list(rows[0].keys()) if rows else [],
            "execution_time": 0.0,
            "overview": answer_text,
            "llm_overview": answer_text,
            "analytics": analytics,
            "proactive_alerts": [],
            "trend_snapshot": {"has_time_series": False, "time_column": None, "weekly_changes": []},
            "tables_used": [],
            "tables_in_scope": [],
            "clarification_questions": [],
            "generation": {"mode": "direct", "provider": "none", "model": "intent-router"},
            "agentic": {
                "mode": "direct-answer",
                "summary": {
                    "selected_connections": 0,
                    "sql_connections": 0,
                    "mongodb_connections": 0,
                    "row_count": len(rows),
                },
                "connections": [],
                "proactive_alerts": [],
                "trend_snapshot": {"has_time_series": False, "time_column": None, "weekly_changes": []},
                "tables_used": [],
                "tables_in_scope": [],
                "clarification_questions": [],
                "intent": {
                    "name": str(direct.get("intent", "direct-answer")),
                    "no_sql_required": True,
                },
            },
        }

    if not _is_analytics_convertible_prompt(prompt):
        return _build_non_analytics_response(
            "I can't generate SQL for this prompt because it is not an analytics request. "
            "Redirecting this to System Assistant is recommended."
        )

    if not is_admin:
        org_limits = get_org_governance_limits((user.organisation or "").strip().lower())
        max_rows_per_connection = min(max_rows_per_connection, int(org_limits.get("max_rows_per_query", max_rows_per_connection)))

    generation_metadata = get_generation_metadata()
    allowed_ids = set(_allowed_connection_ids(user, is_admin))
    if not allowed_ids:
        raise ValueError("No permitted database available")

    selected_ids = [connection_id for connection_id in connection_ids if connection_id in allowed_ids]
    if not selected_ids:
        selected_ids = sorted(allowed_ids)
    selected_ids = _pick_best_connection_ids(prompt, selected_ids)

    generated_queries: list[dict] = []
    agentic_traces: list[dict] = []
    merged_rows: list[dict[str, Any]] = []
    tables_in_scope: list[str] = []
    tables_used: list[str] = []
    clarification_questions: list[str] = []
    zero_row_diagnostics: list[dict[str, Any]] = []

    started = time.perf_counter()

    for connection_id in selected_ids:
        connection_query: dict[str, Any] = {"connection_id": connection_id}
        if org_filter:
            connection_query.update(org_filter)
        connection = connections_collection().find_one(connection_query)
        if not connection:
            continue

        metadata_rows = sorted(
            list(
                metadata_collection()
                .find({"connection_id": connection_id})
                .limit(MAX_METADATA_ROWS_PER_CONNECTION)
            ),
            key=lambda row: (
                normalize_table_name(str(row.get("table_name", ""))),
                str(row.get("column_name", "")).strip().lower(),
                str(row.get("data_type", "")).strip().lower(),
            ),
        )

        if not is_admin:
            org_name = _resolve_user_organisation(user)
            permission_doc = permissions_collection().find_one(
                {
                    "employee_id": user.id,
                    "organisation": {"$regex": f"^{re.escape(org_name)}$", "$options": "i"},
                    "connection_id": connection_id,
                    "can_query": True,
                },
                {"allowed_tables": 1},
            )
            if not permission_doc:
                continue
            all_tables, allowed_set = normalize_allowed_tables((permission_doc or {}).get("allowed_tables", ["*"]))
            if not all_tables:
                metadata_rows = [
                    row
                    for row in metadata_rows
                    if normalize_table_name(str(row.get("table_name", ""))) in allowed_set
                ]
                if not metadata_rows:
                    continue
        else:
            all_tables = True
            allowed_set = set()

        if _is_table_inventory_prompt(prompt):
            inventory_rows = _build_table_inventory_rows(
                connection_id,
                connection.get("name", ""),
                metadata_rows,
            )
            merged_rows.extend(inventory_rows)
            table_names = [row["table_name"] for row in inventory_rows]
            generated_queries.append(
                {
                    "connection_id": connection_id,
                    "connection_name": connection.get("name", ""),
                    "db_type": connection.get("db_type"),
                    "query_language": "system",
                    "query_text": "LIST_ASSIGNED_TABLES",
                }
            )
            tables_in_scope.extend(table_names)
            tables_used.extend(table_names)
            agentic_traces.append(
                {
                    "mode": "small-agent",
                    "planner": {
                        "connection_id": connection_id,
                        "connection_name": connection.get("name", ""),
                        "db_type": connection.get("db_type", ""),
                        "confidence": "high",
                        "matched_tables": [
                            {
                                "table_name": table_name,
                                "score": 1,
                                "column_count": 0,
                                "sample_columns": [],
                            }
                            for table_name in table_names[:5]
                        ],
                        "needs_clarification": False,
                        "clarification_question": None,
                        "guardrails": {"read_only": True, "allowed_tables": [] if all_tables else sorted(allowed_set)},
                    },
                    "policy": {"status": "approved", "max_rows": max_rows_per_connection, "read_only": True},
                    "repair": {"status": "skipped", "attempts": [], "max_attempts": 0},
                    "insight": {
                        "summary": f"Returned {len(table_names)} assigned table(s) from metadata.",
                        "signals": [f"You have access to {len(table_names)} table(s) on this connection."],
                        "proactive_alerts": [],
                        "trend_snapshot": {"has_time_series": False, "time_column": None, "weekly_changes": []},
                        "tables_used": table_names,
                        "tables_in_scope": table_names,
                    },
                }
            )
            continue

        if connection.get("db_type") in {"mysql", "postgresql"}:
            try:
                result = execute_agentic_sql_connection(
                    user,
                    prompt,
                    connection,
                    metadata_rows,
                    all_tables=all_tables,
                    allowed_tables=allowed_set,
                    max_rows=max_rows_per_connection,
                )
            except ValueError as exc:
                message = str(exc)
                if message.lower().startswith("clarification required:"):
                    clarification_questions.append(message.replace("Clarification required:", "", 1).strip())
                    continue
                if "outside permitted scope" in message.lower() or "table-level permission violation" in message.lower():
                    allowed_table_names = sorted(
                        {
                            normalize_table_name(str(item.get("table_name") or ""))
                            for item in metadata_rows
                            if normalize_table_name(str(item.get("table_name") or ""))
                        }
                    )
                    if allowed_table_names:
                        preview = ", ".join(allowed_table_names[:8])
                        clarification_questions.append(
                            f"Use allowed tables for connection {connection_id}: {preview}."
                        )
                    else:
                        clarification_questions.append(
                            f"No permitted tables detected on connection {connection_id}. Ask admin to grant table access."
                        )
                    continue
                clarification_questions.append(
                    f"Connection {connection_id} ({connection.get('name', '')}): {message}"
                )
                continue

            generated_queries.append(
                {
                    "connection_id": connection_id,
                    "connection_name": connection.get("name", ""),
                    "db_type": connection.get("db_type"),
                    "query_language": "sql",
                    "query_text": result["generated_sql"],
                }
            )
            agentic_traces.append(result["agentic"])
            tables_in_scope.extend(result.get("tables_in_scope", []))
            tables_used.extend(result.get("tables_used", []))
            if result.get("zero_row_diagnostic"):
                zero_row_diagnostics.append(
                    {
                        "connection_id": connection_id,
                        "connection_name": connection.get("name", ""),
                        **result.get("zero_row_diagnostic", {}),
                    }
                )

            for row in result["rows"]:
                merged_rows.append(
                    {
                        "connection_id": connection_id,
                        "connection_name": connection.get("name", ""),
                        **row,
                    }
                )
            continue

        if _is_column_inventory_prompt(prompt):
            target_table = _extract_target_table_name(prompt)
            inventory_rows = _build_column_inventory_rows(
                connection_id,
                connection.get("name", ""),
                metadata_rows,
                target_table,
            )
            if not inventory_rows and target_table:
                available_tables = sorted(
                    {
                        normalize_table_name(str(item.get("table_name") or ""))
                        for item in metadata_rows
                        if normalize_table_name(str(item.get("table_name") or ""))
                    }
                )
                if available_tables:
                    clarification_questions.append(
                        f"Table '{target_table}' is not in your assigned scope for connection {connection_id}. Try: {', '.join(available_tables[:8])}."
                    )
                else:
                    clarification_questions.append(
                        f"No tables available in your assigned scope for connection {connection_id}."
                    )
                continue

            merged_rows.extend(inventory_rows)
            referenced_tables = sorted({row["table_name"] for row in inventory_rows})
            generated_queries.append(
                {
                    "connection_id": connection_id,
                    "connection_name": connection.get("name", ""),
                    "db_type": connection.get("db_type"),
                    "query_language": "system",
                    "query_text": "LIST_TABLE_COLUMNS",
                }
            )
            tables_in_scope.extend(referenced_tables)
            tables_used.extend(referenced_tables)
            agentic_traces.append(
                {
                    "mode": "small-agent",
                    "planner": {
                        "connection_id": connection_id,
                        "connection_name": connection.get("name", ""),
                        "db_type": connection.get("db_type", ""),
                        "confidence": "high",
                        "matched_tables": [
                            {
                                "table_name": table_name,
                                "score": 1,
                                "column_count": sum(1 for row in inventory_rows if row["table_name"] == table_name),
                                "sample_columns": [
                                    row["column_name"]
                                    for row in inventory_rows
                                    if row["table_name"] == table_name
                                ][:5],
                            }
                            for table_name in referenced_tables[:5]
                        ],
                        "needs_clarification": False,
                        "clarification_question": None,
                        "guardrails": {"read_only": True, "allowed_tables": [] if all_tables else sorted(allowed_set)},
                    },
                    "policy": {"status": "approved", "max_rows": max_rows_per_connection, "read_only": True},
                    "repair": {"status": "skipped", "attempts": [], "max_attempts": 0},
                    "insight": {
                        "summary": f"Returned {len(inventory_rows)} column definition row(s) from assigned metadata.",
                        "signals": [
                            f"Found {len(referenced_tables)} table(s) in scope for this schema request.",
                            f"Returned columns from {target_table}." if target_table else "Returned columns across assigned tables.",
                        ],
                        "proactive_alerts": [],
                        "trend_snapshot": {"has_time_series": False, "time_column": None, "weekly_changes": []},
                        "tables_used": referenced_tables,
                        "tables_in_scope": referenced_tables,
                    },
                }
            )
            continue

        if connection.get("db_type") == "mongodb":
            collection_name = _pick_mongo_collection(prompt, metadata_rows)
            if not collection_name:
                continue
            filter_doc: dict[str, Any] = {}
            mongo_query_text = json.dumps({"find": collection_name, "filter": filter_doc})
            client = MongoClient(build_mongo_uri(connection))
            database = resolve_mongo_database(client, connection)
            docs = list(database[collection_name].find(filter_doc).limit(max_rows_per_connection))
            generated_queries.append(
                {
                    "connection_id": connection_id,
                    "connection_name": connection.get("name", ""),
                    "db_type": connection.get("db_type"),
                    "query_language": "mongodb",
                    "query_text": mongo_query_text,
                }
            )
            if collection_name:
                if collection_name not in tables_in_scope:
                    tables_in_scope.append(collection_name)
                if collection_name not in tables_used:
                    tables_used.append(collection_name)
            query_logs_collection().insert_one(
                {
                    "organisation": (user.organisation or "").strip().lower(),
                    "employee_id": user.id,
                    "user_prompt": prompt,
                    "generated_sql": mongo_query_text,
                    "execution_time": 0,
                    "created_at": now_utc(),
                }
            )
            for doc in docs:
                merged_rows.append(
                    {
                        "connection_id": connection_id,
                        "connection_name": connection.get("name", ""),
                        **_sanitize_mongo_doc(doc),
                    }
                )
            agentic_traces.append(
                {
                    "mode": "small-agent",
                    "planner": {
                        "connection_id": connection_id,
                        "connection_name": connection.get("name", ""),
                        "db_type": connection.get("db_type", "mongodb"),
                        "confidence": "medium" if collection_name else "low",
                        "matched_tables": [
                            {
                                "table_name": collection_name,
                                "score": 1,
                                "column_count": 0,
                                "sample_columns": [],
                            }
                        ] if collection_name else [],
                        "needs_clarification": False,
                        "clarification_question": None,
                        "guardrails": {"read_only": True, "allowed_tables": []},
                    },
                    "policy": {"status": "approved", "max_rows": max_rows_per_connection, "read_only": True},
                    "repair": {"status": "skipped", "attempts": [], "max_attempts": 0},
                    "insight": {
                        "summary": f"Returned {len(docs)} MongoDB documents from {collection_name}.",
                        "signals": [f"Collection {collection_name} selected for this prompt."],
                        "proactive_alerts": [],
                        "trend_snapshot": {"has_time_series": False, "time_column": None, "weekly_changes": []},
                        "tables_used": [collection_name] if collection_name else [],
                        "tables_in_scope": [collection_name] if collection_name else [],
                    },
                }
            )

    execution_time = time.perf_counter() - started

    if not generated_queries and clarification_questions:
        unique_questions = [question for question in dict.fromkeys(question for question in clarification_questions if question)]
        if unique_questions:
            raise ValueError(f"Could not execute analytics for selected connections: {' | '.join(unique_questions[:3])}")

    analytics = compute_business_analytics(merged_rows)
    llm_overview = summarize_data_overview(prompt, merged_rows, analytics)
    trend_snapshot = build_trend_snapshot(merged_rows, analytics)
    proactive_alerts = build_proactive_alerts(analytics, trend_snapshot)

    for query in generated_queries:
        for table_name in extract_tables_from_sql(query.get("query_text", "")):
            if table_name not in tables_used:
                tables_used.append(table_name)

    seen_scope = set()
    tables_in_scope = [name for name in tables_in_scope if not (name in seen_scope or seen_scope.add(name))]
    seen_used = set()
    tables_used = [name for name in tables_used if not (name in seen_used or seen_used.add(name))]

    business_brief = build_human_business_brief(
        prompt,
        generated_queries,
        analytics,
        proactive_alerts,
        trend_snapshot,
        tables_in_scope,
        tables_used,
    )
    overview = business_brief or (llm_overview or "").strip()

    agentic = {
        "mode": "small-agent",
        "connections": agentic_traces,
        "summary": {
            "selected_connections": len(selected_ids),
            "sql_connections": sum(1 for item in generated_queries if item.get("query_language") == "sql"),
            "mongodb_connections": sum(1 for item in generated_queries if item.get("query_language") == "mongodb"),
            "row_count": len(merged_rows),
        },
        "proactive_alerts": proactive_alerts,
        "trend_snapshot": trend_snapshot,
        "tables_used": tables_used,
        "tables_in_scope": tables_in_scope,
        "clarification_questions": [question for question in dict.fromkeys(question for question in clarification_questions if question)],
        "zero_row_diagnostics": zero_row_diagnostics,
    }

    query_logs_collection().update_many(
        {"employee_id": user.id, "user_prompt": prompt, "execution_time": 0},
        {"$set": {"execution_time": execution_time}},
    )

    return {
        "generated_queries": generated_queries,
        "generated_sql": generated_queries[0]["query_text"] if generated_queries else "",
        "rows": merged_rows,
        "columns": list(merged_rows[0].keys()) if merged_rows else [],
        "execution_time": execution_time,
        "overview": overview,
        "llm_overview": llm_overview,
        "business_brief": business_brief,
        "analytics": analytics,
        "proactive_alerts": proactive_alerts,
        "trend_snapshot": trend_snapshot,
        "tables_used": tables_used,
        "tables_in_scope": tables_in_scope,
        "clarification_questions": [question for question in dict.fromkeys(question for question in clarification_questions if question)],
        "zero_row_diagnostics": zero_row_diagnostics,
        "zero_row_reason": zero_row_diagnostics[0]["reason"] if zero_row_diagnostics else "",
        "generation": generation_metadata,
        "agentic": agentic,
    }
