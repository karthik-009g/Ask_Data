from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from bson import ObjectId
import re

from app.core.dependencies import require_employee
from app.db.mongo import UserDoc, get_users_collection
from app.db.system_store import connections_collection, metadata_collection, permissions_collection
from app.schemas.query import AnalysisRequest, PromptRequest
from app.schemas.user import EmployeeProfileUpdate
from app.services.audit_service import log_audit_event
from app.services.analysis_service import execute_connection_analysis
from app.services.export_service import export_csv, export_excel, export_pdf
from app.services.governance_service import count_employee_exports_today, count_employee_queries_today, get_org_governance_limits
from app.services.table_permission_service import normalize_allowed_tables, normalize_table_name
from app.services.query_service import execute_prompt

router = APIRouter(prefix="/employee", tags=["employee"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/profile")
def get_employee_profile(employee: UserDoc = Depends(require_employee)):
    try:
        employee_oid = ObjectId(employee.id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid employee ID")

    doc = get_users_collection().find_one(
        {"_id": employee_oid, "role": "employee"},
        {
            "full_name": 1,
            "email": 1,
            "position": 1,
            "department": 1,
            "phone": 1,
            "manager_name": 1,
            "location": 1,
            "timezone": 1,
            "preferred_language": 1,
            "bio": 1,
            "organisation": 1,
            "role": 1,
            "created_at": 1,
        },
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Employee profile not found")

    return {
        "id": str(doc.get("_id")),
        "full_name": doc.get("full_name", ""),
        "email": doc.get("email", ""),
        "position": doc.get("position", ""),
        "department": doc.get("department", ""),
        "phone": doc.get("phone", ""),
        "manager_name": doc.get("manager_name", ""),
        "location": doc.get("location", ""),
        "timezone": doc.get("timezone", ""),
        "preferred_language": doc.get("preferred_language", ""),
        "bio": doc.get("bio", ""),
        "organisation": doc.get("organisation", ""),
        "role": doc.get("role", "employee"),
        "created_at": doc.get("created_at"),
    }


@router.patch("/profile")
def update_employee_profile(payload: EmployeeProfileUpdate, employee: UserDoc = Depends(require_employee)):
    try:
        employee_oid = ObjectId(employee.id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid employee ID")

    allowed_fields = {
        "full_name": 120,
        "position": 100,
        "department": 100,
        "phone": 40,
        "manager_name": 120,
        "location": 120,
        "timezone": 80,
        "preferred_language": 60,
        "bio": 600,
    }

    updates: dict[str, str] = {}
    payload_dict = payload.model_dump(exclude_unset=True)
    for key, value in payload_dict.items():
        if key not in allowed_fields:
            continue
        if value is None:
            updates[key] = ""
            continue
        text = str(value).strip()
        max_length = allowed_fields[key]
        if len(text) > max_length:
            raise HTTPException(status_code=400, detail=f"{key} exceeds {max_length} characters")
        updates[key] = text

    if not updates:
        raise HTTPException(status_code=400, detail="No profile fields provided")

    result = get_users_collection().update_one({"_id": employee_oid, "role": "employee"}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Employee profile not found")

    updated = get_users_collection().find_one(
        {"_id": employee_oid, "role": "employee"},
        {
            "full_name": 1,
            "email": 1,
            "position": 1,
            "department": 1,
            "phone": 1,
            "manager_name": 1,
            "location": 1,
            "timezone": 1,
            "preferred_language": 1,
            "bio": 1,
            "organisation": 1,
            "role": 1,
            "created_at": 1,
        },
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Employee profile not found")

    return {
        "message": "Profile updated successfully",
        "profile": {
            "id": str(updated.get("_id")),
            "full_name": updated.get("full_name", ""),
            "email": updated.get("email", ""),
            "position": updated.get("position", ""),
            "department": updated.get("department", ""),
            "phone": updated.get("phone", ""),
            "manager_name": updated.get("manager_name", ""),
            "location": updated.get("location", ""),
            "timezone": updated.get("timezone", ""),
            "preferred_language": updated.get("preferred_language", ""),
            "bio": updated.get("bio", ""),
            "organisation": updated.get("organisation", ""),
            "role": updated.get("role", "employee"),
            "created_at": updated.get("created_at"),
        },
    }


@router.get("/governance-usage")
def get_employee_governance_usage(employee: UserDoc = Depends(require_employee)):
    org = (employee.organisation or "").strip().lower()
    limits = get_org_governance_limits(org)

    queries_today = int(count_employee_queries_today(employee.id))
    exports_today = int(count_employee_exports_today(employee.id, org))

    query_limit = int(limits.get("max_queries_per_employee_per_day", 200))
    export_limit = int(limits.get("max_exports_per_employee_per_day", 30))
    max_rows_per_query = int(limits.get("max_rows_per_query", 500))

    return {
        "organisation": org,
        "employee_id": employee.id,
        "limits": {
            "max_queries_per_employee_per_day": query_limit,
            "max_exports_per_employee_per_day": export_limit,
            "max_rows_per_query": max_rows_per_query,
        },
        "usage": {
            "queries_today": queries_today,
            "exports_today": exports_today,
            "queries_remaining": max(query_limit - queries_today, 0),
            "exports_remaining": max(export_limit - exports_today, 0),
        },
    }


@router.get("/connections")
def get_permitted_connections(employee: UserDoc = Depends(require_employee)):
    org = (employee.organisation or "").strip().lower()
    permission_rows = list(permissions_collection().find({"employee_id": employee.id}))
    allowed_ids = [int(item["connection_id"]) for item in permission_rows if item.get("can_read")]
    if not allowed_ids:
        return []

    permission_map = {int(item["connection_id"]): item for item in permission_rows}

    connections = list(connections_collection().find({"organisation": org, "connection_id": {"$in": allowed_ids}}))
    return [
        {
            "id": int(conn["connection_id"]),
            "name": conn.get("name"),
            "db_type": conn.get("db_type"),
            "database_name": conn.get("database_name"),
            "host": conn.get("host"),
            "port": conn.get("port"),
            "created_at": conn.get("created_at"),
            "permissions": {
                "can_read": bool(permission_map[int(conn["connection_id"])].get("can_read", False)),
                "can_query": bool(permission_map[int(conn["connection_id"])].get("can_query", False)),
                "can_visualize": bool(permission_map[int(conn["connection_id"])].get("can_visualize", False)),
                "can_export": bool(permission_map[int(conn["connection_id"])].get("can_export", False)),
                "allowed_tables": permission_map[int(conn["connection_id"])].get("allowed_tables", ["*"]),
            },
        }
        for conn in sorted(connections, key=lambda item: int(item["connection_id"]))
    ]


@router.get("/schema")
def get_permitted_schema(connection_id: int | None = None, employee: UserDoc = Depends(require_employee)):
    org = (employee.organisation or "").strip().lower()
    org_connection_ids = {
        int(item["connection_id"])
        for item in connections_collection().find({"organisation": org}, {"connection_id": 1})
    }
    allowed_ids = [
        int(item["connection_id"])
        for item in permissions_collection().find({"employee_id": employee.id, "can_read": True}, {"connection_id": 1})
        if int(item["connection_id"]) in org_connection_ids
    ]
    if not allowed_ids:
        return []

    query = {"connection_id": {"$in": allowed_ids}}
    if connection_id is not None:
        if connection_id not in allowed_ids:
            raise HTTPException(status_code=403, detail="No access to selected connection")
        query = {"connection_id": connection_id}

    rows = list(metadata_collection().find(query).sort([("connection_id", 1), ("table_name", 1), ("column_name", 1)]).limit(5000))
    permission_rows = list(
        permissions_collection().find(
            {"employee_id": employee.id, "can_read": True, "connection_id": {"$in": allowed_ids}},
            {"connection_id": 1, "allowed_tables": 1},
        )
    )
    table_scope_by_connection: dict[int, tuple[bool, set[str]]] = {}
    for item in permission_rows:
        connection_key = int(item.get("connection_id", 0))
        table_scope_by_connection[connection_key] = normalize_allowed_tables(item.get("allowed_tables", ["*"]))

    filtered_rows = []
    for item in rows:
        connection_key = int(item.get("connection_id", 0))
        all_tables, allowed_set = table_scope_by_connection.get(connection_key, (True, set()))
        if all_tables:
            filtered_rows.append(item)
            continue
        table_name = normalize_table_name(str(item.get("table_name", "")))
        if table_name in allowed_set:
            filtered_rows.append(item)

    return [
        {
            "id": str(item.get("_id")),
            "connection_id": item.get("connection_id"),
            "schema_name": item.get("schema_name"),
            "table_name": item.get("table_name"),
            "column_name": item.get("column_name"),
            "data_type": item.get("data_type"),
            "relationship_info": item.get("relationship_info"),
        }
        for item in filtered_rows
    ]


@router.post("/query")
@limiter.limit("20/minute")
def run_query(request: Request, payload: PromptRequest, employee: UserDoc = Depends(require_employee)):
    try:
        _ = request
        org = (employee.organisation or "").strip().lower()
        limits = get_org_governance_limits(org)
        query_count_today = count_employee_queries_today(employee.id)
        if query_count_today >= int(limits.get("max_queries_per_employee_per_day", 200)):
            log_audit_event(
                actor_user_id=employee.id,
                actor_role=employee.role,
                organisation=org,
                action="governance.alert.query_limit_exceeded",
                target_type="employee",
                target_id=employee.id,
                details={"query_count_today": query_count_today, "limit": limits.get("max_queries_per_employee_per_day")},
            )
            raise HTTPException(status_code=429, detail="Daily query limit reached")

        query_allowed_ids = {
            int(item["connection_id"])
            for item in permissions_collection().find(
                {
                    "employee_id": employee.id,
                    "organisation": {"$regex": f"^{re.escape(org)}$", "$options": "i"},
                    "can_query": True,
                },
                {"connection_id": 1},
            )
        }
        if not query_allowed_ids:
            raise HTTPException(status_code=403, detail="Query access is disabled for this employee")

        if payload.connection_ids:
            if any(connection_id not in query_allowed_ids for connection_id in payload.connection_ids):
                raise HTTPException(status_code=403, detail="Query access denied for one or more selected connections")
            return execute_connection_analysis(employee, payload.prompt, payload.connection_ids, is_admin=False)

        sql, rows, duration = execute_prompt(employee, payload.prompt)
        return {"generated_sql": sql, "rows": rows, "execution_time": duration, "columns": list(rows[0].keys()) if rows else []}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Query failed: {exc}")


@router.post("/export/{format_type}")
def export_result(format_type: str, payload: PromptRequest, employee: UserDoc = Depends(require_employee)):
    org = (employee.organisation or "").strip().lower()
    limits = get_org_governance_limits(org)
    export_count_today = count_employee_exports_today(employee.id, org)
    if export_count_today >= int(limits.get("max_exports_per_employee_per_day", 30)):
        log_audit_event(
            actor_user_id=employee.id,
            actor_role=employee.role,
            organisation=org,
            action="governance.alert.export_limit_exceeded",
            target_type="employee",
            target_id=employee.id,
            details={"exports_today": export_count_today, "limit": limits.get("max_exports_per_employee_per_day")},
        )
        raise HTTPException(status_code=429, detail="Daily export limit reached")

    export_allowed_ids = {
        int(item["connection_id"])
        for item in permissions_collection().find({"employee_id": employee.id, "can_export": True}, {"connection_id": 1})
    }
    if not export_allowed_ids:
        raise HTTPException(status_code=403, detail="Export access is disabled for this employee")

    if payload.connection_ids:
        if any(connection_id not in export_allowed_ids for connection_id in payload.connection_ids):
            raise HTTPException(status_code=403, detail="Export access denied for one or more selected connections")
        result = execute_connection_analysis(employee, payload.prompt, payload.connection_ids, is_admin=False)
        rows = result["rows"]
    else:
        sql, rows, _ = execute_prompt(employee, payload.prompt)
        _ = sql

    if format_type == "csv":
        content = export_csv(rows)
        log_audit_event(actor_user_id=employee.id, actor_role=employee.role, organisation=org, action="employee.export", target_type="format", target_id="csv", details={"rows": len(rows)})
        return Response(content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=result.csv"})
    if format_type == "excel":
        content = export_excel(rows)
        log_audit_event(actor_user_id=employee.id, actor_role=employee.role, organisation=org, action="employee.export", target_type="format", target_id="excel", details={"rows": len(rows)})
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=result.xlsx"})
    if format_type == "pdf":
        content = export_pdf(rows)
        log_audit_event(actor_user_id=employee.id, actor_role=employee.role, organisation=org, action="employee.export", target_type="format", target_id="pdf", details={"rows": len(rows)})
        return Response(content, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=result.pdf"})
    raise HTTPException(status_code=400, detail="Unsupported format")


@router.post("/analyse")
@limiter.limit("20/minute")
def run_analysis(request: Request, payload: AnalysisRequest, employee: UserDoc = Depends(require_employee)):
    _ = request
    try:
        mode = (payload.mode or "analytics").strip().lower()
        org = (employee.organisation or "").strip().lower()
        limits = get_org_governance_limits(org)
        query_count_today = count_employee_queries_today(employee.id)
        if query_count_today >= int(limits.get("max_queries_per_employee_per_day", 200)):
            log_audit_event(
                actor_user_id=employee.id,
                actor_role=employee.role,
                organisation=org,
                action="governance.alert.query_limit_exceeded",
                target_type="employee",
                target_id=employee.id,
                details={"query_count_today": query_count_today, "limit": limits.get("max_queries_per_employee_per_day")},
            )
            raise HTTPException(status_code=429, detail="Daily query limit reached")

        if mode == "analytics":
            query_allowed_ids = {
                int(item["connection_id"])
                for item in permissions_collection().find({"employee_id": employee.id, "can_query": True}, {"connection_id": 1})
            }
            if not query_allowed_ids:
                raise HTTPException(status_code=403, detail="Query access is disabled for this employee")
            if any(connection_id not in query_allowed_ids for connection_id in payload.connection_ids):
                raise HTTPException(status_code=403, detail="Query access denied for one or more selected connections")

        return execute_connection_analysis(
            employee,
            payload.prompt,
            payload.connection_ids,
            is_admin=False,
            mode=mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Analysis failed: {exc}")


@router.post("/analyse/export/{format_type}")
def export_analysis(format_type: str, payload: AnalysisRequest, employee: UserDoc = Depends(require_employee)):
    org = (employee.organisation or "").strip().lower()
    limits = get_org_governance_limits(org)
    export_count_today = count_employee_exports_today(employee.id, org)
    if export_count_today >= int(limits.get("max_exports_per_employee_per_day", 30)):
        raise HTTPException(status_code=429, detail="Daily export limit reached")

    export_allowed_ids = {
        int(item["connection_id"])
        for item in permissions_collection().find({"employee_id": employee.id, "can_export": True}, {"connection_id": 1})
    }
    if not export_allowed_ids:
        raise HTTPException(status_code=403, detail="Export access is disabled for this employee")
    if any(connection_id not in export_allowed_ids for connection_id in payload.connection_ids):
        raise HTTPException(status_code=403, detail="Export access denied for one or more selected connections")

    try:
        result = execute_connection_analysis(employee, payload.prompt, payload.connection_ids, is_admin=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Analysis failed: {exc}")

    rows = result["rows"]
    if format_type == "csv":
        content = export_csv(rows)
        log_audit_event(actor_user_id=employee.id, actor_role=employee.role, organisation=org, action="employee.analyse.export", target_type="format", target_id="csv", details={"rows": len(rows)})
        return Response(content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=analysis.csv"})
    if format_type == "excel":
        content = export_excel(rows)
        log_audit_event(actor_user_id=employee.id, actor_role=employee.role, organisation=org, action="employee.analyse.export", target_type="format", target_id="excel", details={"rows": len(rows)})
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=analysis.xlsx"})
    if format_type == "pdf":
        content = export_pdf(rows)
        log_audit_event(actor_user_id=employee.id, actor_role=employee.role, organisation=org, action="employee.analyse.export", target_type="format", target_id="pdf", details={"rows": len(rows)})
        return Response(content, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=analysis.pdf"})
    raise HTTPException(status_code=400, detail="Unsupported format")
