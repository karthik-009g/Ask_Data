from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING
from pymongo.collection import Collection

from app.db.mongo import get_mongo_client


def _get_system_db_name() -> str:
    client = get_mongo_client()
    db = client.get_default_database(default="auth_db")
    return db.name


def _collection(name: str) -> Collection:
    client = get_mongo_client()
    db = client[_get_system_db_name()]
    coll = db[name]

    if name == "connections":
        coll.create_index([("connection_id", ASCENDING)], unique=True)
    if name == "permissions":
        coll.create_index([("employee_id", ASCENDING), ("connection_id", ASCENDING)], unique=True)
        coll.create_index([("employee_id", ASCENDING)])
    if name == "metadata_catalog":
        coll.create_index([("connection_id", ASCENDING)])
    if name == "query_logs":
        coll.create_index([("created_at", ASCENDING)])
    if name == "audit_logs":
        coll.create_index([("created_at", ASCENDING)])
        coll.create_index([("organisation", ASCENDING), ("created_at", ASCENDING)])
        coll.create_index([("actor_user_id", ASCENDING), ("created_at", ASCENDING)])
    if name == "permission_change_requests":
        coll.create_index([("organisation", ASCENDING), ("status", ASCENDING), ("created_at", ASCENDING)])
        coll.create_index([("employee_id", ASCENDING), ("created_at", ASCENDING)])
    if name == "scheduled_reports":
        coll.create_index([("organisation", ASCENDING), ("is_active", ASCENDING), ("next_run_at", ASCENDING)])
    if name == "governance_limits":
        coll.create_index([("organisation", ASCENDING)], unique=True)
    if name == "connection_health":
        coll.create_index([("organisation", ASCENDING), ("connection_id", ASCENDING)], unique=True)
        coll.create_index([("checked_at", ASCENDING)])
    if name == "counters":
        coll.create_index([("name", ASCENDING)], unique=True)

    return coll


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def next_sequence(name: str) -> int:
    coll = _collection("counters")
    result = coll.find_one_and_update(
        {"name": name},
        {"$inc": {"value": 1}, "$setOnInsert": {"name": name}},
        upsert=True,
        return_document=True,
    )
    return int(result.get("value", 1))


def connections_collection() -> Collection:
    return _collection("connections")


def permissions_collection() -> Collection:
    return _collection("permissions")


def metadata_collection() -> Collection:
    return _collection("metadata_catalog")


def query_logs_collection() -> Collection:
    return _collection("query_logs")


def audit_logs_collection() -> Collection:
    return _collection("audit_logs")


def permission_change_requests_collection() -> Collection:
    return _collection("permission_change_requests")


def scheduled_reports_collection() -> Collection:
    return _collection("scheduled_reports")


def governance_limits_collection() -> Collection:
    return _collection("governance_limits")


def connection_health_collection() -> Collection:
    return _collection("connection_health")


def serialize_connection(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["connection_id"],
        "name": doc["name"],
        "db_type": doc["db_type"],
        "host": doc.get("host"),
        "port": doc.get("port"),
        "username": doc.get("username"),
        "database_name": doc.get("database_name"),
        "connection_url": doc.get("connection_url"),
        "is_active": doc.get("is_active", True),
        "created_at": doc.get("created_at"),
    }
