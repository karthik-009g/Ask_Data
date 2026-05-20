from datetime import datetime, timezone
import logging
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pymongo.errors import DuplicateKeyError
from sqlalchemy.engine import make_url

from app.core.dependencies import require_admin
from app.core.encryption import encrypt_secret
from app.core.security import hash_password
from app.db.mongo import UserDoc, get_users_collection
from app.db.system_store import (
    audit_logs_collection,
    connection_health_collection,
    connections_collection,
    governance_limits_collection,
    permissions_collection,
    permission_change_requests_collection,
    metadata_collection,
    query_logs_collection,
    scheduled_reports_collection,
    next_sequence,
    now_utc,
    serialize_connection,
)
from app.schemas.auth import RegisterRequest
from app.schemas.connection import DatabaseConnectionCreate, DatabaseConnectionOut, PermissionAssignment
from app.schemas.governance import GovernanceLimitsUpdate, ScheduledReportCreate
from app.schemas.query import AnalysisRequest
from app.schemas.user import UserOut
from app.services.analysis_service import execute_connection_analysis
from app.services.audit_service import log_audit_event
from app.services.ai_service import get_generation_metadata
from app.services.connection_service import test_connection
from app.services.export_service import export_csv, export_excel, export_pdf
from app.services.governance_service import (
    count_employee_queries_today,
    get_org_governance_limits,
    upsert_org_governance_limits,
)
from app.services.metadata_service import refresh_metadata
from app.services.permission_workflow_service import apply_employee_permissions
from app.services.table_permission_service import normalize_allowed_tables, normalize_table_name
from app.utils.password_validator import PasswordValidator

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


def _normalize_admin_org(current_admin: UserDoc) -> str:
    organisation = (current_admin.organisation or "").strip().lower()
    if not organisation:
        raise HTTPException(status_code=400, detail="Admin organisation is required")
    return organisation


def _admin_connection_scope(current_admin: UserDoc) -> dict:
    return {"organisation": _normalize_admin_org(current_admin)}


@router.get("/model-runtime")
def get_model_runtime(_: UserDoc = Depends(require_admin)):
    metadata = get_generation_metadata()
    return {
        "mode": metadata.get("mode"),
        "provider": metadata.get("provider"),
        "model": metadata.get("model"),
    }


@router.get("/profile")
def get_admin_profile(current_admin: UserDoc = Depends(require_admin)):
    org = _normalize_admin_org(current_admin)
    doc = get_users_collection().find_one(
        {"_id": ObjectId(current_admin.id), "role": "admin", "organisation": org},
        {"full_name": 1, "email": 1, "organisation": 1, "role": 1},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Admin profile not found")

    return {
        "id": str(doc.get("_id")),
        "full_name": doc.get("full_name", ""),
        "email": doc.get("email", ""),
        "organisation": doc.get("organisation", ""),
        "role": doc.get("role", "admin"),
    }


def _sanitize_connection_payload(payload: DatabaseConnectionCreate) -> DatabaseConnectionCreate:
    if payload.method != "url" or not payload.connection_url:
        return payload

    db_type = payload.db_type.lower()
    if db_type in {"mysql", "postgresql"}:
        parsed = make_url(payload.connection_url)
        return DatabaseConnectionCreate(
            name=payload.name,
            db_type=payload.db_type,
            method=payload.method,
            host=parsed.host,
            port=parsed.port,
            username=parsed.username,
            password=parsed.password,
            database_name=parsed.database,
            connection_url=str(parsed.set(password=None)),
        )

    if db_type == "mongodb":
        parsed = urlparse(payload.connection_url)
        username = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port
        db_name_from_url = (parsed.path.lstrip("/") if parsed.path else None) or None
        db_name = db_name_from_url or (payload.database_name.strip() if payload.database_name else None)
        if not db_name:
            raise HTTPException(
                status_code=400,
                detail="MongoDB database name is required. Add it in the URL path or fill the Database Name field.",
            )
        if username and host:
            netloc = f"{username}@{host}"
            if port:
                netloc = f"{netloc}:{port}"
            url_path = parsed.path if (parsed.path and parsed.path != "/") else (f"/{db_name}" if db_name else "")
            safe_url = urlunparse((parsed.scheme, netloc, url_path, parsed.params, parsed.query, parsed.fragment))
        else:
            safe_url = payload.connection_url
        return DatabaseConnectionCreate(
            name=payload.name,
            db_type=payload.db_type,
            method=payload.method,
            host=host,
            port=port,
            username=username,
            password=password,
            database_name=db_name,
            connection_url=safe_url,
        )

    return payload


@router.get("/employees", response_model=list[UserOut])
def list_employees(current_admin: UserDoc = Depends(require_admin)):
    coll = get_users_collection()
    docs = coll.find(
        {"role": "employee", "organisation": current_admin.organisation},
        {
            "email": 1,
            "full_name": 1,
            "position": 1,
            "department": 1,
            "phone": 1,
            "manager_name": 1,
            "location": 1,
            "timezone": 1,
            "preferred_language": 1,
            "bio": 1,
            "role": 1,
        },
    )
    return [
        UserOut(
            id=str(d["_id"]),
            email=d["email"],
            full_name=d["full_name"],
            position=d.get("position"),
            department=d.get("department"),
            phone=d.get("phone"),
            manager_name=d.get("manager_name"),
            location=d.get("location"),
            timezone=d.get("timezone"),
            preferred_language=d.get("preferred_language"),
            bio=d.get("bio"),
            role=d["role"],
        )
        for d in docs
    ]


@router.post("/employees", response_model=UserOut)
def create_employee(payload: RegisterRequest, current_admin: UserDoc = Depends(require_admin)):
    if payload.role != "employee":
        raise HTTPException(status_code=400, detail="Only employee role allowed in this endpoint")

    organisation = _normalize_admin_org(current_admin)

    email = payload.email.strip().lower()
    position = payload.position.strip() if payload.position else ""

    # Validate password strength
    is_valid, missing = PasswordValidator.validate(payload.password)
    if not is_valid:
        error_msg = PasswordValidator.get_error_message(missing)
        raise HTTPException(status_code=400, detail=error_msg)

    coll = get_users_collection()
    try:
        result = coll.insert_one(
            {
                "organisation": organisation,
                "email": email,
                "full_name": payload.full_name,
                "position": position,
                "hashed_password": hash_password(payload.password),
                "role": "employee",
                "created_at": datetime.now(timezone.utc),
            }
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Email already exists")
    log_audit_event(
        actor_user_id=current_admin.id,
        actor_role=current_admin.role,
        organisation=organisation,
        action="employee.created",
        target_type="employee",
        target_id=str(result.inserted_id),
        details={"email": email, "position": position},
    )
    return UserOut(id=str(result.inserted_id), email=email, full_name=payload.full_name, position=position, role="employee")


@router.delete("/employees/{employee_id}")
def delete_employee(employee_id: str, current_admin: UserDoc = Depends(require_admin)):
    try:
        employee_oid = ObjectId(employee_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid employee ID")

    users_coll = get_users_collection()
    employee_doc = users_coll.find_one(
        {"_id": employee_oid, "role": "employee", "organisation": _normalize_admin_org(current_admin)}
    )
    if not employee_doc:
        raise HTTPException(status_code=404, detail="Employee not found in your organisation")

    users_result = users_coll.delete_one({"_id": employee_oid, "role": "employee"})
    permissions_result = permissions_collection().delete_many({"employee_id": employee_id})
    logs_result = query_logs_collection().delete_many({"employee_id": employee_id})

    log_audit_event(
        actor_user_id=current_admin.id,
        actor_role=current_admin.role,
        organisation=_normalize_admin_org(current_admin),
        action="employee.deleted",
        target_type="employee",
        target_id=employee_id,
        details={
            "users": int(users_result.deleted_count),
            "permissions": int(permissions_result.deleted_count),
            "query_logs": int(logs_result.deleted_count),
        },
    )

    return {
        "message": "Employee removed",
        "deleted": {
            "users": int(users_result.deleted_count),
            "permissions": int(permissions_result.deleted_count),
            "query_logs": int(logs_result.deleted_count),
        },
    }


@router.post("/connections", response_model=DatabaseConnectionOut)
def create_connection(payload: DatabaseConnectionCreate, current_admin: UserDoc = Depends(require_admin)):
    if payload.db_type not in {"mysql", "postgresql", "mongodb"}:
        raise HTTPException(status_code=400, detail="Unsupported db_type")
    if payload.method not in {"form", "url"}:
        raise HTTPException(status_code=400, detail="Unsupported method")

    payload = _sanitize_connection_payload(payload)
    encrypted_password = encrypt_secret(payload.password) if payload.password else None

    connection_doc = {
        "connection_id": next_sequence("connections"),
        "organisation": _normalize_admin_org(current_admin),
        "name": payload.name,
        "db_type": payload.db_type,
        "host": payload.host,
        "port": payload.port,
        "username": payload.username,
        "encrypted_password": encrypted_password,
        "database_name": payload.database_name,
        "connection_url": payload.connection_url,
        "is_active": True,
        "created_at": now_utc(),
    }

    try:
        test_connection(connection_doc)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Connection test failed: {exc}")

    connections_collection().insert_one(connection_doc)

    try:
        refresh_metadata(connection_doc)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Connection saved, metadata extraction failed: {exc}")

    log_audit_event(
        actor_user_id=current_admin.id,
        actor_role=current_admin.role,
        organisation=_normalize_admin_org(current_admin),
        action="connection.created",
        target_type="connection",
        target_id=str(connection_doc["connection_id"]),
        details={"name": connection_doc.get("name"), "db_type": connection_doc.get("db_type")},
    )

    return DatabaseConnectionOut(**serialize_connection(connection_doc))


@router.post("/connections/test")
def test_connection_only(payload: DatabaseConnectionCreate, _: UserDoc = Depends(require_admin)):
    payload = _sanitize_connection_payload(payload)
    encrypted_password = encrypt_secret(payload.password) if payload.password else None
    connection_doc = {
        "name": payload.name,
        "db_type": payload.db_type,
        "host": payload.host,
        "port": payload.port,
        "username": payload.username,
        "encrypted_password": encrypted_password,
        "database_name": payload.database_name,
        "connection_url": payload.connection_url,
    }
    try:
        test_connection(connection_doc)
        return {"message": "Connection successful"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Connection test failed: {exc}")


@router.put("/connections/{connection_id}", response_model=DatabaseConnectionOut)
def update_connection(connection_id: int, payload: DatabaseConnectionCreate, current_admin: UserDoc = Depends(require_admin)):
    coll = connections_collection()
    current = coll.find_one({"connection_id": connection_id, **_admin_connection_scope(current_admin)})
    if not current:
        raise HTTPException(status_code=404, detail="Connection not found")

    payload = _sanitize_connection_payload(payload)

    update_doc = {
        "name": payload.name,
        "db_type": payload.db_type,
        "host": payload.host,
        "port": payload.port,
        "username": payload.username,
        "database_name": payload.database_name,
        "connection_url": payload.connection_url,
    }
    if payload.password:
        update_doc["encrypted_password"] = encrypt_secret(payload.password)
    else:
        update_doc["encrypted_password"] = current.get("encrypted_password")

    test_doc = {**current, **update_doc}
    try:
        test_connection(test_doc)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Connection test failed: {exc}")

    coll.update_one({"connection_id": connection_id, **_admin_connection_scope(current_admin)}, {"$set": update_doc})
    updated = coll.find_one({"connection_id": connection_id, **_admin_connection_scope(current_admin)})

    try:
        refresh_metadata(updated)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Connection updated, metadata extraction failed: {exc}")

    return DatabaseConnectionOut(**serialize_connection(updated))


@router.get("/connections", response_model=list[DatabaseConnectionOut])
def get_connections(current_admin: UserDoc = Depends(require_admin)):
    return [
        DatabaseConnectionOut(**serialize_connection(item))
        for item in connections_collection().find(_admin_connection_scope(current_admin)).sort("connection_id", 1)
    ]


@router.delete("/connections/{connection_id}")
def delete_connection(connection_id: int, current_admin: UserDoc = Depends(require_admin)):
    coll = connections_collection()
    conn = coll.find_one({"connection_id": connection_id, **_admin_connection_scope(current_admin)})
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    coll.delete_one({"connection_id": connection_id, **_admin_connection_scope(current_admin)})
    metadata_collection().delete_many({"connection_id": connection_id})
    permissions_collection().delete_many({"connection_id": connection_id})
    log_audit_event(
        actor_user_id=current_admin.id,
        actor_role=current_admin.role,
        organisation=_normalize_admin_org(current_admin),
        action="connection.deleted",
        target_type="connection",
        target_id=str(connection_id),
        details={"name": conn.get("name", "")},
    )
    return {"message": "Deleted"}


@router.post("/permissions")
def assign_permissions(payload: PermissionAssignment, current_admin: UserDoc = Depends(require_admin)):
    coll = get_users_collection()
    try:
        oid = ObjectId(payload.employee_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid employee ID")

    employee = coll.find_one({"_id": oid, "role": "employee", "organisation": current_admin.organisation})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found in your organisation")

    org_connection_ids = {
        int(row["connection_id"])
        for row in connections_collection().find(_admin_connection_scope(current_admin), {"connection_id": 1})
    }

    if not payload.permissions and not payload.connection_ids:
        raise HTTPException(status_code=400, detail="Select at least one connection to assign")

    docs: list[dict] = []
    if payload.permissions:
        for entry in payload.permissions:
            if int(entry.connection_id) not in org_connection_ids:
                raise HTTPException(status_code=403, detail="Cannot assign permissions for connections outside your organisation")

            all_tables, allowed_set = normalize_allowed_tables(entry.allowed_tables)
            if not all_tables:
                valid_tables = {
                    normalize_table_name(str(item.get("table_name", "")))
                    for item in metadata_collection().find({"connection_id": int(entry.connection_id)}, {"table_name": 1})
                }
                valid_tables.discard("")
                invalid_tables = sorted(table for table in allowed_set if table not in valid_tables)
                if invalid_tables:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid table selections for connection {entry.connection_id}: {', '.join(invalid_tables)}",
                    )

            docs.append(
                {
                    "employee_id": payload.employee_id,
                    "connection_id": entry.connection_id,
                    "can_read": entry.can_read,
                    "can_query": entry.can_query,
                    "can_visualize": entry.can_visualize,
                    "can_export": entry.can_export,
                    "allowed_tables": ["*"] if all_tables else sorted(allowed_set),
                }
            )
    else:
        for connection_id in payload.connection_ids:
            if int(connection_id) not in org_connection_ids:
                raise HTTPException(status_code=403, detail="Cannot assign permissions for connections outside your organisation")
            docs.append(
                {
                    "employee_id": payload.employee_id,
                    "connection_id": connection_id,
                    "can_read": True,
                    "can_query": True,
                    "can_visualize": True,
                    "can_export": True,
                    "allowed_tables": ["*"],
                }
            )

    if not docs:
        raise HTTPException(status_code=400, detail="No permission entries to apply")

    applied_count = apply_employee_permissions(_normalize_admin_org(current_admin), payload.employee_id, docs)

    log_audit_event(
        actor_user_id=current_admin.id,
        actor_role=current_admin.role,
        organisation=_normalize_admin_org(current_admin),
        action="permissions.assigned",
        target_type="employee",
        target_id=payload.employee_id,
        details={"entries": applied_count},
    )
    return {"message": "Permissions assigned", "employee_id": payload.employee_id, "entries": applied_count}


@router.get("/employees/{employee_id}/permissions")
def get_employee_permissions(employee_id: str, current_admin: UserDoc = Depends(require_admin)):
    logger.info(
        "permissions lookup requested employee_id=%s admin_id=%s admin_org=%s",
        employee_id,
        current_admin.id,
        current_admin.organisation,
    )

    try:
        oid = ObjectId(employee_id)
    except Exception:
        logger.warning("permissions lookup invalid employee id=%s", employee_id)
        raise HTTPException(status_code=400, detail="Invalid employee ID")

    employee = get_users_collection().find_one({"_id": oid, "role": "employee", "organisation": current_admin.organisation})
    if not employee:
        logger.warning("permissions lookup employee not found employee_id=%s admin_org=%s", employee_id, current_admin.organisation)
        raise HTTPException(status_code=404, detail="Employee not found in your organisation")

    org_connection_ids = {
        int(row["connection_id"])
        for row in connections_collection().find(_admin_connection_scope(current_admin), {"connection_id": 1})
    }
    rows = [
        row
        for row in permissions_collection().find({"employee_id": employee_id}).sort("connection_id", 1)
        if int(row.get("connection_id", -1)) in org_connection_ids
    ]
    logger.info("permissions lookup success employee_id=%s rows=%s", employee_id, len(rows))
    return [
        {
            "connection_id": int(row["connection_id"]),
            "can_read": bool(row.get("can_read", False)),
            "can_query": bool(row.get("can_query", False)),
            "can_visualize": bool(row.get("can_visualize", False)),
            "can_export": bool(row.get("can_export", False)),
            "allowed_tables": row.get("allowed_tables", ["*"]),
        }
        for row in rows
    ]


@router.post("/connections/{connection_id}/refresh-metadata")
def refresh_connection_metadata(connection_id: int, current_admin: UserDoc = Depends(require_admin)):
    conn = connections_collection().find_one({"connection_id": connection_id, **_admin_connection_scope(current_admin)})
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    count = refresh_metadata(conn)
    return {"message": "Metadata refreshed", "entries": count}


@router.get("/query-logs")
def get_query_logs(current_admin: UserDoc = Depends(require_admin)):
    org = _normalize_admin_org(current_admin)
    employee_ids = [
        str(item["_id"])
        for item in get_users_collection().find({"organisation": org}, {"_id": 1})
    ]
    logs = list(query_logs_collection().find({"employee_id": {"$in": employee_ids}}).sort("created_at", -1).limit(20))
    return [
        {
            "id": str(log.get("_id")),
            "employee_id": log.get("employee_id"),
            "user_prompt": log.get("user_prompt"),
            "generated_sql": log.get("generated_sql"),
            "execution_time": log.get("execution_time", 0),
            "timestamp": log.get("created_at"),
        }
        for log in logs
    ]


@router.get("/metadata")
def get_metadata(connection_id: int | None = None, current_admin: UserDoc = Depends(require_admin)):
    org_connection_ids = [
        int(row["connection_id"])
        for row in connections_collection().find(_admin_connection_scope(current_admin), {"connection_id": 1})
    ]
    query = {"connection_id": {"$in": org_connection_ids}}
    if connection_id is not None:
        if connection_id not in org_connection_ids:
            raise HTTPException(status_code=403, detail="No access to selected connection")
        query = {"connection_id": connection_id}
    rows = list(metadata_collection().find(query).sort([("connection_id", 1), ("table_name", 1), ("column_name", 1)]).limit(5000))
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
        for item in rows
    ]


@router.get("/permission-requests")
def list_permission_requests(status: str = "", current_admin: UserDoc = Depends(require_admin)):
    org = _normalize_admin_org(current_admin)
    query: dict = {"organisation": org}
    if status:
        query["status"] = status.strip().lower()
    rows = list(permission_change_requests_collection().find(query).sort("created_at", -1).limit(200))
    return [
        {
            "id": str(item.get("_id")),
            "request_id": item.get("request_id"),
            "employee_id": item.get("employee_id"),
            "requested_by": item.get("requested_by"),
            "status": item.get("status"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "decision_note": item.get("decision_note", ""),
            "permissions": item.get("permissions", []),
        }
        for item in rows
    ]


@router.get("/audit-logs")
def get_audit_timeline(limit: int = 200, current_admin: UserDoc = Depends(require_admin)):
    org = _normalize_admin_org(current_admin)
    capped = min(max(limit, 1), 1000)
    rows = list(audit_logs_collection().find({"organisation": org}).sort("created_at", -1).limit(capped))
    return [
        {
            "id": str(item.get("_id")),
            "actor_user_id": item.get("actor_user_id"),
            "actor_role": item.get("actor_role"),
            "action": item.get("action"),
            "target_type": item.get("target_type"),
            "target_id": item.get("target_id"),
            "details": item.get("details", {}),
            "created_at": item.get("created_at"),
        }
        for item in rows
    ]


@router.get("/governance-limits")
def get_governance_limits(current_admin: UserDoc = Depends(require_admin)):
    org = _normalize_admin_org(current_admin)
    return get_org_governance_limits(org)


@router.get("/governance-usage")
def get_governance_usage(current_admin: UserDoc = Depends(require_admin)):
    org = _normalize_admin_org(current_admin)
    limits = get_org_governance_limits(org)
    employees = list(
        get_users_collection().find(
            {"organisation": org, "role": "employee"},
            {"_id": 1, "full_name": 1, "email": 1},
        )
    )

    usage_rows = []
    total_queries = 0
    total_exports = 0
    for employee in employees:
        employee_id = str(employee.get("_id"))
        query_count = query_logs_collection().count_documents(
            {
                "employee_id": employee_id,
                "created_at": {"$gte": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)},
            }
        )
        export_count = audit_logs_collection().count_documents(
            {
                "organisation": org,
                "actor_user_id": employee_id,
                "action": {"$in": ["employee.export", "employee.analyse.export"]},
                "created_at": {"$gte": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)},
            }
        )
        total_queries += int(query_count)
        total_exports += int(export_count)
        usage_rows.append(
            {
                "employee_id": employee_id,
                "full_name": employee.get("full_name", ""),
                "email": employee.get("email", ""),
                "queries_today": int(query_count),
                "query_limit": int(limits.get("max_queries_per_employee_per_day", 200)),
                "exports_today": int(export_count),
                "export_limit": int(limits.get("max_exports_per_employee_per_day", 30)),
            }
        )

    return {
        "organisation": org,
        "limits": limits,
        "summary": {
            "employees": len(usage_rows),
            "queries_today_total": int(total_queries),
            "exports_today_total": int(total_exports),
        },
        "employees": usage_rows,
    }


@router.put("/governance-limits")
def update_governance_limits(payload: GovernanceLimitsUpdate, current_admin: UserDoc = Depends(require_admin)):
    org = _normalize_admin_org(current_admin)
    values = upsert_org_governance_limits(org, payload.model_dump())
    log_audit_event(
        actor_user_id=current_admin.id,
        actor_role=current_admin.role,
        organisation=org,
        action="governance.updated",
        target_type="governance_limits",
        target_id=org,
        details=values,
    )
    return {"message": "Governance limits updated", "limits": values}


@router.get("/scheduled-reports")
def list_scheduled_reports(current_admin: UserDoc = Depends(require_admin)):
    org = _normalize_admin_org(current_admin)
    rows = list(scheduled_reports_collection().find({"organisation": org}).sort("created_at", -1).limit(200))
    return [
        {
            "id": str(item.get("_id")),
            "report_id": item.get("report_id"),
            "name": item.get("name"),
            "format": item.get("format"),
            "interval_minutes": item.get("interval_minutes"),
            "is_active": bool(item.get("is_active", True)),
            "next_run_at": item.get("next_run_at"),
            "last_run_at": item.get("last_run_at"),
            "last_status": item.get("last_status", ""),
            "recipient_email": item.get("recipient_email", ""),
        }
        for item in rows
    ]


@router.post("/scheduled-reports")
def create_scheduled_report(payload: ScheduledReportCreate, current_admin: UserDoc = Depends(require_admin)):
    org = _normalize_admin_org(current_admin)
    fmt = (payload.format or "csv").strip().lower()
    if fmt not in {"csv", "pdf"}:
        raise HTTPException(status_code=400, detail="Scheduled reports support csv or pdf format")

    report_id = next_sequence("scheduled_reports")
    row = {
        "report_id": report_id,
        "organisation": org,
        "created_by": current_admin.id,
        "name": payload.name.strip() or f"Report {report_id}",
        "prompt": payload.prompt,
        "connection_ids": payload.connection_ids,
        "format": fmt,
        "interval_minutes": payload.interval_minutes,
        "recipient_email": payload.recipient_email.strip(),
        "is_active": True,
        "next_run_at": now_utc(),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    scheduled_reports_collection().insert_one(row)
    log_audit_event(
        actor_user_id=current_admin.id,
        actor_role=current_admin.role,
        organisation=org,
        action="scheduled_report.created",
        target_type="scheduled_report",
        target_id=str(report_id),
        details={"name": row["name"], "format": fmt, "interval_minutes": payload.interval_minutes},
    )
    return {"message": "Scheduled report created", "report_id": report_id}


@router.post("/scheduled-reports/{report_id}/run")
def run_scheduled_report_now(report_id: int, current_admin: UserDoc = Depends(require_admin)):
    org = _normalize_admin_org(current_admin)
    coll = scheduled_reports_collection()
    row = coll.find_one({"report_id": report_id, "organisation": org})
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled report not found")

    try:
        result = execute_connection_analysis(current_admin, row.get("prompt", ""), row.get("connection_ids", []), is_admin=True)
        rows = result.get("rows", [])
        content = export_csv(rows) if row.get("format") == "csv" else export_pdf(rows)
        ext = "csv" if row.get("format") == "csv" else "pdf"
        reports_dir = Path(__file__).resolve().parents[4] / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        file_path = reports_dir / f"scheduled-report-{report_id}-{int(now_utc().timestamp())}.{ext}"
        file_path.write_bytes(content)
        coll.update_one(
            {"report_id": report_id, "organisation": org},
            {
                "$set": {
                    "last_run_at": now_utc(),
                    "last_status": "success",
                    "last_file": str(file_path),
                    "next_run_at": now_utc(),
                    "updated_at": now_utc(),
                }
            },
        )
        log_audit_event(
            actor_user_id=current_admin.id,
            actor_role=current_admin.role,
            organisation=org,
            action="scheduled_report.ran",
            target_type="scheduled_report",
            target_id=str(report_id),
            details={"file": str(file_path), "rows": len(rows)},
        )
        return FileResponse(path=str(file_path), filename=file_path.name)
    except Exception as exc:
        coll.update_one(
            {"report_id": report_id, "organisation": org},
            {"$set": {"last_run_at": now_utc(), "last_status": f"failed: {exc}", "updated_at": now_utc()}},
        )
        raise HTTPException(status_code=502, detail=f"Scheduled report execution failed: {exc}")


@router.get("/connection-health")
def connection_health_dashboard(refresh: bool = False, current_admin: UserDoc = Depends(require_admin)):
    org = _normalize_admin_org(current_admin)
    rows = list(connections_collection().find({"organisation": org}).sort("connection_id", 1))
    if not refresh:
        cached = list(connection_health_collection().find({"organisation": org}).sort("connection_id", 1))
        if cached:
            return [
                {
                    "connection_id": int(item.get("connection_id", 0)),
                    "connection_name": item.get("connection_name", ""),
                    "db_type": item.get("db_type", ""),
                    "status": item.get("status", "unknown"),
                    "detail": item.get("detail", ""),
                    "checked_at": item.get("checked_at"),
                }
                for item in cached
            ]
    results = []
    for conn in rows:
        status = "healthy"
        detail = "ok"
        checked_at = now_utc()
        try:
            test_connection(conn)
        except Exception as exc:
            status = "down"
            detail = str(exc)
        connection_health_collection().update_one(
            {"organisation": org, "connection_id": int(conn.get("connection_id", 0))},
            {
                "$set": {
                    "connection_name": conn.get("name", ""),
                    "db_type": conn.get("db_type", ""),
                    "status": status,
                    "detail": detail,
                    "checked_at": checked_at,
                }
            },
            upsert=True,
        )
        results.append(
            {
                "connection_id": int(conn.get("connection_id", 0)),
                "connection_name": conn.get("name", ""),
                "db_type": conn.get("db_type", ""),
                "status": status,
                "detail": detail,
                "checked_at": checked_at,
            }
        )
    return results


@router.post("/analyse")
def run_admin_analysis(payload: AnalysisRequest, admin: UserDoc = Depends(require_admin)):
    mode = (payload.mode or "analytics").strip().lower()
    org = _normalize_admin_org(admin)
    limits = get_org_governance_limits(org)
    query_count_today = count_employee_queries_today(admin.id)
    query_limit = int(limits.get("max_queries_per_employee_per_day", 200))
    if query_count_today >= query_limit:
        raise HTTPException(status_code=429, detail="Daily analysis query limit reached")

    try:
        return execute_connection_analysis(admin, payload.prompt, payload.connection_ids, is_admin=True, mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("admin analysis failed")
        raise HTTPException(status_code=502, detail=f"Analysis failed: {exc}")


@router.post("/analyse/export/{format_type}")
def export_admin_analysis(format_type: str, payload: AnalysisRequest, admin: UserDoc = Depends(require_admin)):
    org = _normalize_admin_org(admin)
    limits = get_org_governance_limits(org)
    export_limit = int(limits.get("max_exports_per_employee_per_day", 30))
    exports_today = audit_logs_collection().count_documents(
        {
            "organisation": org,
            "actor_user_id": admin.id,
            "action": "admin.analyse.export",
            "created_at": {"$gte": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)},
        }
    )
    if int(exports_today) >= export_limit:
        raise HTTPException(status_code=429, detail="Daily analysis export limit reached")

    try:
        result = execute_connection_analysis(admin, payload.prompt, payload.connection_ids, is_admin=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("admin export analysis failed")
        raise HTTPException(status_code=502, detail=f"Analysis failed: {exc}")

    rows = result["rows"]
    if format_type == "csv":
        content = export_csv(rows)
        log_audit_event(actor_user_id=admin.id, actor_role=admin.role, organisation=org, action="admin.analyse.export", target_type="format", target_id="csv", details={"rows": len(rows)})
        return Response(content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=admin-analysis.csv"})
    if format_type == "excel":
        content = export_excel(rows)
        log_audit_event(actor_user_id=admin.id, actor_role=admin.role, organisation=org, action="admin.analyse.export", target_type="format", target_id="excel", details={"rows": len(rows)})
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=admin-analysis.xlsx"})
    if format_type == "pdf":
        content = export_pdf(rows)
        log_audit_event(actor_user_id=admin.id, actor_role=admin.role, organisation=org, action="admin.analyse.export", target_type="format", target_id="pdf", details={"rows": len(rows)})
        return Response(content, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=admin-analysis.pdf"})
    raise HTTPException(status_code=400, detail="Unsupported format")


@router.get("/analysis-usage")
def get_admin_analysis_usage(current_admin: UserDoc = Depends(require_admin)):
    org = _normalize_admin_org(current_admin)
    limits = get_org_governance_limits(org)

    query_limit = int(limits.get("max_queries_per_employee_per_day", 200))
    export_limit = int(limits.get("max_exports_per_employee_per_day", 30))
    max_rows_per_query = int(limits.get("max_rows_per_query", 500))

    queries_today = int(count_employee_queries_today(current_admin.id))
    exports_today = int(
        audit_logs_collection().count_documents(
            {
                "organisation": org,
                "actor_user_id": current_admin.id,
                "action": "admin.analyse.export",
                "created_at": {"$gte": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)},
            }
        )
    )

    return {
        "organisation": org,
        "admin_id": current_admin.id,
        "limits": {
            "max_queries_per_day": query_limit,
            "max_exports_per_day": export_limit,
            "max_rows_per_query": max_rows_per_query,
        },
        "usage": {
            "queries_today": queries_today,
            "exports_today": exports_today,
            "queries_remaining": max(query_limit - queries_today, 0),
            "exports_remaining": max(export_limit - exports_today, 0),
        },
    }
