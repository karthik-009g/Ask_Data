from __future__ import annotations

from typing import Any

import pytest
from bson import ObjectId

from app.db.mongo import UserDoc
from app.services import connection_service as cs
from app.services import query_service as qs


class _Cursor:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = list(rows)

    def limit(self, n: int):
        self._rows = self._rows[:n]
        return self

    def __iter__(self):
        return iter(self._rows)


class _Collection:
    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self.rows = list(rows or [])

    def find(self, query: dict[str, Any] | None = None, projection: dict[str, int] | None = None):
        _ = projection
        return _Cursor([row for row in self.rows if self._matches(row, query or {})])

    def find_one(self, query: dict[str, Any], projection: dict[str, int] | None = None):
        _ = projection
        for row in self.rows:
            if self._matches(row, query):
                return dict(row)
        return None

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


class _PermissionCollection(_Collection):
    def find_one(self, query: dict[str, Any], projection: dict[str, int] | None = None):
        _ = query
        _ = projection
        # Simulate permission revocation between initial allow-list fetch and execution-time lookup.
        return None


def test_execute_prompt_blocks_when_permission_doc_disappears(monkeypatch):
    employee_oid = ObjectId("64b64b64b64b64b64b64b642")
    employee = UserDoc(
        {
            "_id": employee_oid,
            "email": "employee@acme.com",
            "full_name": "Emp One",
            "role": "employee",
            "organisation": "acme",
        }
    )

    connections = _Collection(
        [
            {
                "connection_id": 1,
                "organisation": "acme",
                "db_type": "postgresql",
                "name": "acme-main",
            }
        ]
    )
    permissions = _PermissionCollection(
        [
            {
                "employee_id": str(employee_oid),
                "organisation": "acme",
                "connection_id": 1,
                "can_query": True,
                "allowed_tables": ["orders"],
            }
        ]
    )
    metadata = _Collection(
        [
            {
                "connection_id": 1,
                "table_name": "orders",
                "column_name": "order_id",
                "data_type": "integer",
            }
        ]
    )

    monkeypatch.setattr(qs, "try_build_direct_answer", lambda user, prompt: None)
    monkeypatch.setattr(qs, "connections_collection", lambda: connections)
    monkeypatch.setattr(qs, "permissions_collection", lambda: permissions)
    monkeypatch.setattr(qs, "metadata_collection", lambda: metadata)
    monkeypatch.setattr(qs, "get_org_governance_limits", lambda org: {"max_rows_per_query": 100})

    def _fail_if_called(*args, **kwargs):
        _ = args
        _ = kwargs
        raise AssertionError("execute_agentic_sql_connection should not run without a current permission doc")

    monkeypatch.setattr(qs, "execute_agentic_sql_connection", _fail_if_called)

    with pytest.raises(ValueError, match="No permitted database available"):
        qs.execute_prompt(employee, "show me latest orders")


def test_mongodb_test_connection_closes_client(monkeypatch):
    state = {"closed": False, "pinged": False}

    class _FakeAdmin:
        def command(self, cmd: str):
            assert cmd == "ping"
            state["pinged"] = True
            return {"ok": 1}

    class _FakeMongoClient:
        def __init__(self, uri: str, serverSelectionTimeoutMS: int):
            _ = uri
            _ = serverSelectionTimeoutMS
            self.admin = _FakeAdmin()

        def close(self):
            state["closed"] = True

    monkeypatch.setattr(cs, "MongoClient", _FakeMongoClient)
    monkeypatch.setattr(cs, "build_mongo_uri", lambda connection: "mongodb://localhost:27017/test")

    cs.test_connection({"db_type": "mongodb"})

    assert state["pinged"] is True
    assert state["closed"] is True
