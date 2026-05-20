from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from app.core.dependencies import require_super_admin
from app.core.security import hash_password
from app.db.mongo import UserDoc, get_users_collection
from app.db.system_store import (
    audit_logs_collection,
    connection_health_collection,
    connections_collection,
    metadata_collection,
    permission_change_requests_collection,
    permissions_collection,
    query_logs_collection,
)
from app.schemas.auth import RegisterRequest
from app.schemas.governance import GovernanceLimitsUpdate, PermissionDecisionPayload
from app.services.audit_service import log_audit_event
from app.services.connection_service import test_connection
from app.services.governance_service import upsert_org_governance_limits
from app.services.permission_workflow_service import apply_employee_permissions
from app.utils.password_validator import PasswordValidator

router = APIRouter(prefix="/super-admin", tags=["super-admin"])


def _normalize_org_name(organisation: str) -> str:
    return organisation.strip().lower()


def _build_safe_super_admin_org_context() -> dict[str, Any]:
    users_coll = get_users_collection()

    organisation_rows = list(
        users_coll.aggregate(
            [
                {"$match": {"role": {"$in": ["admin", "employee"]}}},
                {
                    "$group": {
                        "_id": {"$ifNull": ["$organisation", ""]},
                        "employee_count": {
                            "$sum": {
                                "$cond": [{"$eq": ["$role", "employee"]}, 1, 0],
                            }
                        },
                        "admin_count": {
                            "$sum": {
                                "$cond": [{"$eq": ["$role", "admin"]}, 1, 0],
                            }
                        },
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

    organisations = []
    for item in organisation_rows:
        organisation = str(item.get("_id") or "").strip().lower()
        if not organisation:
            continue
        organisations.append(
            {
                "organisation": organisation,
                "admin_count": int(item.get("admin_count", 0)),
                "employee_count": int(item.get("employee_count", 0)),
                "database_count": connection_map.get(organisation, 0),
            }
        )

    known_orgs = {item["organisation"] for item in organisations}
    for organisation, database_count in connection_map.items():
        if organisation and organisation not in known_orgs:
            organisations.append(
                {
                    "organisation": organisation,
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


@router.get("/metrics")
def get_super_admin_metrics(_: UserDoc = Depends(require_super_admin)):
    users_coll = get_users_collection()
    connections_coll = connections_collection()

    admin_count = users_coll.count_documents({"role": "admin"})

    organisation_rows = list(
        users_coll.aggregate(
            [
                {"$match": {"role": {"$in": ["admin", "employee"]}}},
                {
                    "$group": {
                        "_id": {"$ifNull": ["$organisation", ""]},
                        "employee_count": {
                            "$sum": {
                                "$cond": [{"$eq": ["$role", "employee"]}, 1, 0],
                            }
                        },
                        "admin_count": {
                            "$sum": {
                                "$cond": [{"$eq": ["$role", "admin"]}, 1, 0],
                            }
                        },
                    }
                },
                {"$sort": {"_id": 1}},
            ]
        )
    )

    connection_rows = list(
        connections_coll.aggregate(
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

    organisations = []
    for item in organisation_rows:
        organisation = str(item.get("_id") or "").strip().lower()
        if not organisation:
            continue
        organisations.append(
            {
                "organisation": organisation,
                "admin_count": int(item.get("admin_count", 0)),
                "employee_count": int(item.get("employee_count", 0)),
                "database_count": connection_map.get(organisation, 0),
            }
        )

    orphan_connection_orgs = [
        org for org in connection_map.keys() if org and org not in {item["organisation"] for item in organisations}
    ]
    for organisation in sorted(orphan_connection_orgs):
        organisations.append(
            {
                "organisation": organisation,
                "admin_count": 0,
                "employee_count": 0,
                "database_count": connection_map[organisation],
            }
        )

    return {
        "admin_count": admin_count,
        "organisation_count": len(organisations),
        "organisations": organisations,
    }


@router.post("/admins")
def create_admin(payload: RegisterRequest, _: UserDoc = Depends(require_super_admin)):
    if payload.role != "admin":
        raise HTTPException(status_code=400, detail="Only admin role can be provisioned here")

    organisation = payload.organisation.strip().lower()
    if not organisation:
        raise HTTPException(status_code=400, detail="Organisation is required")

    is_valid, missing = PasswordValidator.validate(payload.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=PasswordValidator.get_error_message(missing))

    email = payload.email.strip().lower()
    users_coll = get_users_collection()
    try:
        users_coll.insert_one(
            {
                "organisation": organisation,
                "email": email,
                "full_name": payload.full_name,
                "hashed_password": hash_password(payload.password),
                "role": "admin",
                "created_at": datetime.now(timezone.utc),
            }
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Email already exists")

    log_audit_event(
        actor_user_id="system-super-admin",
        actor_role="super_admin",
        organisation=organisation,
        action="admin.created",
        target_type="admin",
        target_id=email,
        details={"email": email},
    )

    return {"message": "Admin created"}


@router.delete("/admins/{admin_id}")
def remove_admin(admin_id: str, _: UserDoc = Depends(require_super_admin)):
    users_coll = get_users_collection()

    try:
        admin_oid = ObjectId(admin_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid admin ID")

    admin_doc = users_coll.find_one({"_id": admin_oid, "role": "admin"})
    if not admin_doc:
        raise HTTPException(status_code=404, detail="Admin not found")

    deleted = users_coll.delete_one({"_id": admin_oid, "role": "admin"})
    query_logs_collection().delete_many({"employee_id": admin_id})

    log_audit_event(
        actor_user_id="system-super-admin",
        actor_role="super_admin",
        organisation=str(admin_doc.get("organisation") or "").strip().lower(),
        action="admin.deleted",
        target_type="admin",
        target_id=admin_id,
        details={"email": admin_doc.get("email", "")},
    )

    return {
        "message": "Admin removed",
        "organisation": str(admin_doc.get("organisation") or "").strip().lower(),
        "deleted": int(deleted.deleted_count),
    }


@router.get("/organisations/details")
def get_organisation_details(organisation: str, _: UserDoc = Depends(require_super_admin)):
    org = _normalize_org_name(organisation)
    if not org:
        raise HTTPException(status_code=400, detail="Organisation is required")

    users_coll = get_users_collection()
    connections_coll = connections_collection()

    admin_rows = list(
        users_coll.find(
            {"organisation": org, "role": "admin"},
            {"email": 1, "full_name": 1, "created_at": 1, "role": 1},
        ).sort("created_at", 1)
    )
    employee_count = users_coll.count_documents({"organisation": org, "role": "employee"})

    database_rows = list(
        connections_coll.find(
            {"organisation": org},
            {"connection_id": 1, "name": 1, "db_type": 1, "database_name": 1, "host": 1, "created_at": 1},
        ).sort("connection_id", 1)
    )

    return {
        "organisation": org,
        "admin_credentials": [
            {
                "id": str(item.get("_id")),
                "full_name": item.get("full_name", ""),
                "email": item.get("email", ""),
                "role": item.get("role", "admin"),
                "created_at": item.get("created_at"),
            }
            for item in admin_rows
        ],
        "employee_count": int(employee_count),
        "database_count": len(database_rows),
        "databases": [
            {
                "connection_id": int(item.get("connection_id", 0)),
                "name": item.get("name", ""),
                "db_type": item.get("db_type", ""),
                "database_name": item.get("database_name"),
                "host": item.get("host"),
                "created_at": item.get("created_at"),
            }
            for item in database_rows
        ],
    }


@router.delete("/organisations")
def remove_organisation(organisation: str, _: UserDoc = Depends(require_super_admin)):
    org = _normalize_org_name(organisation)
    if not org:
        raise HTTPException(status_code=400, detail="Organisation is required")

    users_coll = get_users_collection()
    connections_coll = connections_collection()
    permissions_coll = permissions_collection()
    metadata_coll = metadata_collection()
    logs_coll = query_logs_collection()

    user_docs = list(users_coll.find({"organisation": org, "role": {"$in": ["admin", "employee"]}}, {"_id": 1, "role": 1}))
    user_ids = [str(item.get("_id")) for item in user_docs if item.get("_id")]
    employee_ids = [str(item.get("_id")) for item in user_docs if item.get("_id") and item.get("role") == "employee"]

    connection_ids = [
        int(item.get("connection_id"))
        for item in connections_coll.find({"organisation": org}, {"connection_id": 1})
        if item.get("connection_id") is not None
    ]

    users_result = users_coll.delete_many({"organisation": org, "role": {"$in": ["admin", "employee"]}})
    conn_result = connections_coll.delete_many({"organisation": org})

    if connection_ids:
        metadata_result = metadata_coll.delete_many({"connection_id": {"$in": connection_ids}})
        permissions_by_conn_result = permissions_coll.delete_many({"connection_id": {"$in": connection_ids}})
    else:
        metadata_result = metadata_coll.delete_many({"connection_id": -1})
        permissions_by_conn_result = permissions_coll.delete_many({"connection_id": -1})

    if employee_ids:
        permissions_by_employee_result = permissions_coll.delete_many({"employee_id": {"$in": employee_ids}})
    else:
        permissions_by_employee_result = permissions_coll.delete_many({"employee_id": "__none__"})

    logs_result = logs_coll.delete_many({"$or": [{"organisation": org}, {"employee_id": {"$in": user_ids}}]})

    log_audit_event(
        actor_user_id="system-super-admin",
        actor_role="super_admin",
        organisation=org,
        action="organisation.deleted",
        target_type="organisation",
        target_id=org,
        details={
            "users": int(users_result.deleted_count),
            "connections": int(conn_result.deleted_count),
            "metadata": int(metadata_result.deleted_count),
            "permissions": int(permissions_by_conn_result.deleted_count + permissions_by_employee_result.deleted_count),
            "query_logs": int(logs_result.deleted_count),
        },
    )

    return {
        "message": f"Organisation '{org}' removed",
        "deleted": {
            "users": int(users_result.deleted_count),
            "connections": int(conn_result.deleted_count),
            "metadata": int(metadata_result.deleted_count),
            "permissions": int(permissions_by_conn_result.deleted_count + permissions_by_employee_result.deleted_count),
            "query_logs": int(logs_result.deleted_count),
        },
    }


@router.get("/permission-requests")
def list_permission_requests(status: str = "pending", _: UserDoc = Depends(require_super_admin)):
    query: dict = {}
    if status:
        query["status"] = status.strip().lower()
    rows = list(permission_change_requests_collection().find(query).sort("created_at", -1).limit(500))
    return [
        {
            "id": str(item.get("_id")),
            "request_id": item.get("request_id"),
            "organisation": item.get("organisation"),
            "requested_by": item.get("requested_by"),
            "employee_id": item.get("employee_id"),
            "permissions": item.get("permissions", []),
            "status": item.get("status"),
            "decision_note": item.get("decision_note", ""),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        for item in rows
    ]


@router.post("/permission-requests/{request_id}/approve")
def approve_permission_request(request_id: int, payload: PermissionDecisionPayload, _: UserDoc = Depends(require_super_admin)):
    coll = permission_change_requests_collection()
    row = coll.find_one({"request_id": request_id})
    if not row:
        raise HTTPException(status_code=404, detail="Permission request not found")
    if row.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Permission request already processed")

    applied_count = apply_employee_permissions(row.get("organisation", ""), row.get("employee_id", ""), row.get("permissions", []))
    coll.update_one(
        {"request_id": request_id},
        {"$set": {"status": "approved", "decision_note": payload.note, "approved_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}},
    )

    log_audit_event(
        actor_user_id="system-super-admin",
        actor_role="super_admin",
        organisation=row.get("organisation", ""),
        action="permissions.approved",
        target_type="permission_change_request",
        target_id=str(request_id),
        details={"employee_id": row.get("employee_id", ""), "applied_entries": applied_count},
    )
    return {"message": "Permission request approved", "applied_entries": applied_count}


@router.post("/permission-requests/{request_id}/reject")
def reject_permission_request(request_id: int, payload: PermissionDecisionPayload, _: UserDoc = Depends(require_super_admin)):
    coll = permission_change_requests_collection()
    row = coll.find_one({"request_id": request_id})
    if not row:
        raise HTTPException(status_code=404, detail="Permission request not found")
    if row.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Permission request already processed")

    coll.update_one(
        {"request_id": request_id},
        {"$set": {"status": "rejected", "decision_note": payload.note, "rejected_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}},
    )

    log_audit_event(
        actor_user_id="system-super-admin",
        actor_role="super_admin",
        organisation=row.get("organisation", ""),
        action="permissions.rejected",
        target_type="permission_change_request",
        target_id=str(request_id),
        details={"employee_id": row.get("employee_id", ""), "note": payload.note},
    )
    return {"message": "Permission request rejected"}


@router.get("/audit-logs")
def get_global_audit_timeline(limit: int = 500, _: UserDoc = Depends(require_super_admin)):
    capped = min(max(limit, 1), 2000)
    rows = list(audit_logs_collection().find({}).sort("created_at", -1).limit(capped))
    return [
        {
            "id": str(item.get("_id")),
            "organisation": item.get("organisation", ""),
            "actor_user_id": item.get("actor_user_id", ""),
            "actor_role": item.get("actor_role", ""),
            "action": item.get("action", ""),
            "target_type": item.get("target_type", ""),
            "target_id": item.get("target_id", ""),
            "details": item.get("details", {}),
            "created_at": item.get("created_at"),
        }
        for item in rows
    ]


@router.put("/organisations/{organisation}/governance-limits")
def update_organisation_governance(organisation: str, payload: GovernanceLimitsUpdate, _: UserDoc = Depends(require_super_admin)):
    org = _normalize_org_name(organisation)
    if not org:
        raise HTTPException(status_code=400, detail="Organisation is required")
    values = upsert_org_governance_limits(org, payload.model_dump())
    log_audit_event(
        actor_user_id="system-super-admin",
        actor_role="super_admin",
        organisation=org,
        action="governance.updated",
        target_type="governance_limits",
        target_id=org,
        details=values,
    )
    return {"message": "Governance limits updated", "limits": values}


@router.get("/connection-health")
def global_connection_health(refresh: bool = False, _: UserDoc = Depends(require_super_admin)):
    rows = list(connections_collection().find({}).sort([("organisation", 1), ("connection_id", 1)]))
    if not refresh:
        cached = list(connection_health_collection().find({}).sort([("organisation", 1), ("connection_id", 1)]))
        if cached:
            return [
                {
                    "organisation": str(item.get("organisation") or "").strip().lower(),
                    "connection_id": int(item.get("connection_id", 0)),
                    "connection_name": item.get("connection_name", ""),
                    "db_type": item.get("db_type", ""),
                    "status": item.get("status", "unknown"),
                    "detail": item.get("detail", ""),
                    "checked_at": item.get("checked_at"),
                }
                for item in cached
            ]
    output = []
    for conn in rows:
        org = str(conn.get("organisation") or "").strip().lower()
        status = "healthy"
        detail = "ok"
        checked_at = datetime.now(timezone.utc)
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
        output.append(
            {
                "organisation": org,
                "connection_id": int(conn.get("connection_id", 0)),
                "connection_name": conn.get("name", ""),
                "db_type": conn.get("db_type", ""),
                "status": status,
                "detail": detail,
                "checked_at": checked_at,
            }
        )
    return output
