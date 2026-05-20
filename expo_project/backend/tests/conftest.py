from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Iterable

import pytest
from bson import ObjectId


class FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = list(rows)

    def sort(self, *args, **kwargs):
        if args and isinstance(args[0], list):
            for key, direction in reversed(args[0]):
                self._rows.sort(key=lambda row: row.get(key), reverse=direction == -1)
            return self

        key = args[0] if args else kwargs.get("key")
        direction = args[1] if len(args) > 1 else kwargs.get("direction", 1)
        if key:
            self._rows.sort(key=lambda row: row.get(key), reverse=direction == -1)
        return self

    def limit(self, n: int):
        self._rows = self._rows[:n]
        return self

    def __iter__(self):
        return iter(self._rows)


@dataclass
class _InsertResult:
    inserted_id: Any


@dataclass
class _DeleteResult:
    deleted_count: int


@dataclass
class _UpdateResult:
    matched_count: int


class FakeCollection:
    def __init__(self, rows: Iterable[dict[str, Any]] | None = None):
        self.rows = list(rows or [])

    def find(self, query: dict[str, Any] | None = None, projection: dict[str, int] | None = None):
        matched = [self._project(row, projection) for row in self.rows if self._matches(row, query or {})]
        return FakeCursor(matched)

    def find_one(self, query: dict[str, Any], projection: dict[str, int] | None = None):
        for row in self.rows:
            if self._matches(row, query):
                return self._project(row, projection)
        return None

    def insert_one(self, row: dict[str, Any]):
        doc = dict(row)
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.rows.append(doc)
        return _InsertResult(inserted_id=doc["_id"])

    def delete_one(self, query: dict[str, Any]):
        for idx, row in enumerate(self.rows):
            if self._matches(row, query):
                self.rows.pop(idx)
                return _DeleteResult(deleted_count=1)
        return _DeleteResult(deleted_count=0)

    def delete_many(self, query: dict[str, Any]):
        before = len(self.rows)
        self.rows = [row for row in self.rows if not self._matches(row, query)]
        return _DeleteResult(deleted_count=before - len(self.rows))

    def update_one(self, query: dict[str, Any], update: dict[str, Any]):
        for row in self.rows:
            if self._matches(row, query):
                set_doc = update.get("$set", {})
                row.update(set_doc)
                return _UpdateResult(matched_count=1)
        return _UpdateResult(matched_count=0)

    def _project(self, row: dict[str, Any], projection: dict[str, int] | None):
        if not projection:
            return dict(row)
        keys = [key for key, include in projection.items() if include]
        if not keys:
            return {}
        out = {key: row.get(key) for key in keys}
        if "_id" in row and ("_id" in projection or 1 in projection.values()):
            out.setdefault("_id", row.get("_id"))
        return out

    def _matches(self, row: dict[str, Any], query: dict[str, Any]):
        for key, expected in query.items():
            value = row.get(key)
            if isinstance(expected, dict):
                if "$in" in expected and value not in expected["$in"]:
                    return False
                if "$regex" in expected:
                    import re

                    regex = expected["$regex"]
                    flags = re.IGNORECASE if "i" in str(expected.get("$options", "")) else 0
                    if not re.search(regex, str(value or ""), flags):
                        return False
                continue
            if value != expected:
                return False
        return True


@pytest.fixture
def admin_user():
    return {
        "_id": ObjectId("64b64b64b64b64b64b64b641"),
        "email": "admin@acme.com",
        "full_name": "Admin One",
        "role": "admin",
        "organisation": "acme",
    }


@pytest.fixture
def employee_user():
    return {
        "_id": ObjectId("64b64b64b64b64b64b64b642"),
        "email": "employee@acme.com",
        "full_name": "Emp One",
        "role": "employee",
        "organisation": "acme",
    }


@pytest.fixture
def other_org_employee():
    return {
        "_id": ObjectId("64b64b64b64b64b64b64b643"),
        "email": "other@globex.com",
        "full_name": "Globex User",
        "role": "employee",
        "organisation": "globex",
    }


@pytest.fixture
def userdoc_factory():
    def _factory(doc: dict[str, Any]):
        from app.db.mongo import UserDoc

        return UserDoc(doc)

    return _factory


@pytest.fixture
def fake_db(monkeypatch, admin_user, employee_user, other_org_employee):
    from app.services.system_assistant import api_router as ar

    users = FakeCollection([admin_user, employee_user, other_org_employee])
    permissions = FakeCollection(
        [
            {
                "employee_id": str(employee_user["_id"]),
                "organisation": "acme",
                "connection_id": 1,
                "can_read": True,
                "can_query": False,
                "can_visualize": False,
                "can_export": True,
                "allowed_tables": ["customers"],
            }
        ]
    )
    connections = FakeCollection(
        [
            {
                "connection_id": 1,
                "organisation": "acme",
                "name": "acme-main",
                "db_type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "username": "user",
                "database_name": "clg",
                "connection_url": None,
                "is_active": True,
            },
            {
                "connection_id": 2,
                "organisation": "globex",
                "name": "globex-main",
                "db_type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "username": "user",
                "database_name": "db",
                "connection_url": None,
                "is_active": True,
            },
        ]
    )
    metadata = FakeCollection(
        [
            {
                "connection_id": 1,
                "table_name": "customers",
                "column_name": "customer_id",
                "data_type": "integer",
            },
            {
                "connection_id": 1,
                "table_name": "customers",
                "column_name": "name",
                "data_type": "text",
            },
            {
                "connection_id": 2,
                "table_name": "secrets",
                "column_name": "value",
                "data_type": "text",
            },
        ]
    )
    query_logs = FakeCollection(
        [
            {
                "_id": ObjectId(),
                "employee_id": str(employee_user["_id"]),
                "organisation": "acme",
                "user_prompt": "show x",
                "execution_time": 0.12,
                "created_at": "2026-01-01",
            }
        ]
    )

    monkeypatch.setattr(ar, "get_users_collection", lambda: users)
    monkeypatch.setattr(ar, "permissions_collection", lambda: permissions)
    monkeypatch.setattr(ar, "connections_collection", lambda: connections)
    monkeypatch.setattr(ar, "metadata_collection", lambda: metadata)
    monkeypatch.setattr(ar, "query_logs_collection", lambda: query_logs)
    monkeypatch.setattr(ar, "test_connection", lambda connection: None)
    monkeypatch.setattr(ar, "refresh_metadata", lambda connection: 1)
    monkeypatch.setattr(ar, "next_sequence", lambda name: 99)
    monkeypatch.setattr(ar, "encrypt_secret", lambda value: f"enc:{value}")
    monkeypatch.setattr(ar, "hash_password", lambda value: f"hash:{value}")
    monkeypatch.setattr(ar, "apply_employee_permissions", lambda org, employee_id, docs: len(docs))

    return SimpleNamespace(
        users=users,
        permissions=permissions,
        connections=connections,
        metadata=metadata,
        query_logs=query_logs,
    )
