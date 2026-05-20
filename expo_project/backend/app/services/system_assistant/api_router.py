from datetime import datetime, timezone
import re
import secrets
import string
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.encryption import encrypt_secret
from app.core.security import hash_password
from app.db.mongo import UserDoc, get_users_collection
from app.db.system_store import (
    connections_collection,
    metadata_collection,
    next_sequence,
    permissions_collection,
    query_logs_collection,
    serialize_connection,
)
from app.services.connection_service import test_connection
from app.services.metadata_service import refresh_metadata
from app.services.permission_workflow_service import apply_employee_permissions
from app.services.table_permission_service import normalize_allowed_tables, normalize_table_name
from app.utils.password_validator import PasswordValidator


class SystemApiRouter:
    """Intent-to-operation router for the system control assistant."""

    def route_intent(self, intent: str, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        handlers = {
            "admin_list_employees": self._admin_list_employees,
            "admin_create_employee": self._admin_create_employee,
            "admin_delete_employee": self._admin_delete_employee,
            "admin_list_connections": self._admin_list_connections,
            "admin_create_connection": self._admin_create_connection,
            "admin_update_connection": self._admin_update_connection,
            "admin_delete_connection": self._admin_delete_connection,
            "admin_assign_permission": self._admin_assign_permission,
            "admin_view_access": self._admin_view_access,
            "admin_view_metadata": self._admin_view_metadata,
            "admin_view_logs": self._admin_view_logs,
            "list_tables": self._list_tables,
            "describe_table": self._describe_table,
            "list_columns": self._list_columns,
            "employee_list_connections": self._employee_list_connections,
            "employee_view_schema": self._employee_view_schema,
            "employee_permission_issue": self._employee_permission_issue,
            "employee_request_access": self._employee_request_access,
            "employee_help": self._employee_help,
            "employee_export_request": self._employee_export_request,
            "greeting": self._greeting,
            "small_talk": self._small_talk,
            "help_general": self._help_general,
            "capability_query": self._capability_query,
            "org_info": self._org_info,
            "clarification_needed": self._clarification_needed,
            "follow_up": self._follow_up,
            "security_blocked": self._security_blocked,
        }

        handler = handlers.get(intent)
        if not handler:
            raise ValueError(f"Unsupported intent: {intent}")
        return handler(user=user, entities=entities, user_query=user_query)

    def _org(self, user: UserDoc) -> str:
        org = (user.organisation or "").strip().lower()
        if not org:
            raise ValueError("User organisation is required")
        return org

    def _admin_list_employees(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = entities
        _ = user_query
        org = self._org(user)
        rows = list(
            get_users_collection().find(
                {"role": "employee", "organisation": org},
                {"full_name": 1, "email": 1, "position": 1, "department": 1, "created_at": 1},
            )
        )
        employees = [
            {
                "employee_id": str(row.get("_id")),
                "full_name": row.get("full_name", ""),
                "email": row.get("email", ""),
                "position": row.get("position", ""),
                "department": row.get("department", ""),
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]
        return {
            "response_type": "info",
            "message": f"Found {len(employees)} employee(s) in your organisation.",
            "data": {"employees": employees},
            "next_steps": ["Use employee_id or email to delete/update an employee."],
        }

    def _admin_create_employee(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user_query
        org = self._org(user)
        email = (entities.get("email") or "").strip().lower()
        full_name = (entities.get("full_name") or "").strip() or email.split("@")[0] if email else ""
        if not email:
            if "new employee" in (user_query or "").strip().lower():
                return {
                    "response_type": "action",
                    "message": "I can create an employee. Please provide an email address.",
                    "data": {},
                    "next_steps": ["Create employee with email test@example.com"],
                }
            raise ValueError("Employee email is required. Example: Add employee jane@org.com")

        temp_password = self._generate_temp_password()
        is_valid, missing = PasswordValidator.validate(temp_password)
        if not is_valid:
            raise ValueError(f"Server temporary password policy mismatch: {missing}")

        doc = {
            "organisation": org,
            "email": email,
            "full_name": full_name,
            "position": "",
            "hashed_password": hash_password(temp_password),
            "role": "employee",
            "created_at": datetime.now(timezone.utc),
        }
        try:
            result = get_users_collection().insert_one(doc)
        except DuplicateKeyError:
            raise ValueError("Employee email already exists in your organisation")

        return {
            "response_type": "action",
            "message": "Employee created successfully.",
            "data": {
                "employee_id": str(result.inserted_id),
                "email": email,
                "full_name": full_name,
                "temporary_password_set": True,
            },
            "next_steps": [
                "Ask the employee to reset password after first login.",
                "Assign permissions using: assign permission employee <email> connection <id>.",
            ],
        }

    def _admin_delete_employee(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user_query
        org = self._org(user)
        email = (entities.get("email") or "").strip().lower()
        employee_id = (entities.get("employee_id") or "").strip()

        users_coll = get_users_collection()
        employee_doc = None
        if employee_id:
            try:
                employee_doc = users_coll.find_one({"_id": ObjectId(employee_id), "role": "employee", "organisation": org})
            except Exception:
                raise ValueError("Invalid employee_id")
        elif email:
            employee_doc = users_coll.find_one({"email": email, "role": "employee", "organisation": org})
        else:
            raise ValueError("Provide employee email or employee_id to delete")

        if not employee_doc:
            raise ValueError("Employee not found in your organisation")

        employee_id_str = str(employee_doc.get("_id"))
        users_coll.delete_one({"_id": employee_doc.get("_id")})
        permissions_collection().delete_many({"employee_id": employee_id_str, "organisation": org})
        query_logs_collection().delete_many({"employee_id": employee_id_str, "organisation": org})

        return {
            "response_type": "action",
            "message": "Employee deleted successfully.",
            "data": {"employee_id": employee_id_str, "email": employee_doc.get("email", "")},
            "next_steps": ["Run 'list employees' to verify remaining users."],
        }

    def _admin_list_connections(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = entities
        _ = user_query
        org = self._org(user)
        rows = list(connections_collection().find({"organisation": org}).sort("connection_id", 1))
        serialized = [serialize_connection(row) for row in rows]
        return {
            "response_type": "info",
            "message": f"Found {len(serialized)} connection(s).",
            "data": {"connections": serialized},
            "next_steps": ["Use connection id for update/delete actions."],
        }

    def _admin_create_connection(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user_query
        org = self._org(user)
        payload = entities.get("connection_payload") or {}

        required = {"name", "db_type", "method"}
        missing = [field for field in required if not payload.get(field)]
        if missing:
            normalized = (user_query or "").strip().lower()
            if any(token in normalized for token in {"mysql", "postgres", "postgresql", "mongodb", "mongo"}):
                return {
                    "response_type": "action",
                    "message": "I can add that connection. Please provide connection details like name, host, username, and database.",
                    "data": {},
                    "next_steps": [
                        "Add connection with name=<name> db_type=<mysql|postgresql|mongodb> method=form host=<host> port=<port> username=<user> password=<pwd> database_name=<db>",
                    ],
                }
            raise ValueError(
                "Missing fields for connection creation: "
                + ", ".join(missing)
                + ". Use command-style input: name=... db_type=... method=form ..."
            )

        db_type = str(payload.get("db_type") or "").strip().lower()
        if db_type not in {"mysql", "postgresql", "mongodb"}:
            raise ValueError("Unsupported db_type. Use mysql, postgresql, or mongodb")

        connection_doc = {
            "connection_id": next_sequence("connections"),
            "organisation": org,
            "name": str(payload.get("name") or "").strip(),
            "db_type": db_type,
            "host": payload.get("host"),
            "port": payload.get("port"),
            "username": payload.get("username"),
            "encrypted_password": encrypt_secret(str(payload.get("password"))) if payload.get("password") else None,
            "database_name": payload.get("database_name"),
            "connection_url": payload.get("connection_url"),
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
        }

        test_connection(connection_doc)
        connections_collection().insert_one(connection_doc)
        refresh_metadata(connection_doc)

        return {
            "response_type": "action",
            "message": "Connection created and metadata refreshed.",
            "data": {"connection": serialize_connection(connection_doc)},
            "next_steps": ["Use 'view metadata' to verify imported schema."],
        }

    def _admin_update_connection(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user_query
        org = self._org(user)
        connection_id = entities.get("connection_id")
        payload = entities.get("connection_payload") or {}
        if not connection_id:
            return {
                "response_type": "action",
                "message": "I can update connection credentials. Please share connection id and new fields.",
                "data": {},
                "next_steps": ["Update connection credentials connection_id=45 username=new_user password=new_password"],
            }

        current = connections_collection().find_one({"connection_id": int(connection_id), "organisation": org})
        if not current:
            raise ValueError("Connection not found")

        update_doc = {
            "name": payload.get("name", current.get("name")),
            "db_type": payload.get("db_type", current.get("db_type")),
            "host": payload.get("host", current.get("host")),
            "port": payload.get("port", current.get("port")),
            "username": payload.get("username", current.get("username")),
            "database_name": payload.get("database_name", current.get("database_name")),
            "connection_url": payload.get("connection_url", current.get("connection_url")),
            "encrypted_password": current.get("encrypted_password"),
        }
        if payload.get("password"):
            update_doc["encrypted_password"] = encrypt_secret(str(payload.get("password")))

        test_doc = {**current, **update_doc}
        test_connection(test_doc)
        connections_collection().update_one({"connection_id": int(connection_id), "organisation": org}, {"$set": update_doc})
        updated = connections_collection().find_one({"connection_id": int(connection_id), "organisation": org})
        if not updated:
            raise ValueError("Connection update failed")
        refresh_metadata(updated)

        return {
            "response_type": "action",
            "message": "Connection updated and metadata refreshed.",
            "data": {"connection": serialize_connection(updated)},
            "next_steps": ["Run 'list connections' to confirm latest settings."],
        }

    def _admin_delete_connection(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user_query
        org = self._org(user)
        connection_id = entities.get("connection_id")
        if not connection_id:
            raise ValueError("Connection id is required for deletion")

        result = connections_collection().delete_one({"connection_id": int(connection_id), "organisation": org})
        if result.deleted_count == 0:
            raise ValueError("Connection not found")

        metadata_collection().delete_many({"connection_id": int(connection_id)})
        permissions_collection().delete_many({"connection_id": int(connection_id), "organisation": org})

        return {
            "response_type": "action",
            "message": "Connection deleted successfully.",
            "data": {"connection_id": int(connection_id)},
            "next_steps": ["Reassign permissions for employees if needed."],
        }

    def _admin_assign_permission(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user_query
        org = self._org(user)
        connection_id = entities.get("connection_id")
        if not connection_id:
            raise ValueError("Connection id is required for permission assignment")

        employee_doc = self._resolve_employee(org=org, entities=entities)
        if not employee_doc:
            raise ValueError("Employee not found in your organisation")

        employee_id = str(employee_doc.get("_id"))
        conn = connections_collection().find_one({"connection_id": int(connection_id), "organisation": org})
        if not conn:
            raise ValueError("Connection not found in your organisation")

        flags = entities.get("permissions") or {}
        docs = [
            {
                "connection_id": int(connection_id),
                "can_read": bool(flags.get("can_read", True)),
                "can_query": bool(flags.get("can_query", False)),
                "can_visualize": bool(flags.get("can_visualize", False)),
                "can_export": bool(flags.get("can_export", False)),
                "allowed_tables": ["*"],
            }
        ]
        applied = apply_employee_permissions(org, employee_id, docs)

        return {
            "response_type": "action",
            "message": "Permissions assigned.",
            "data": {
                "employee_id": employee_id,
                "connection_id": int(connection_id),
                "applied_entries": applied,
            },
            "next_steps": ["Employee can now list assigned connections and schema."],
        }

    def _admin_view_access(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user_query
        org = self._org(user)
        rows = list(permissions_collection().find({"organisation": org}, {"employee_id": 1, "connection_id": 1}))
        if not rows:
            return {
                "response_type": "info",
                "message": "No access assignments found.",
                "data": {"employees": []},
                "next_steps": ["Assign access using: give access to employee <id> for connection <id>"],
            }

        employee_ids = sorted({str(row.get("employee_id")) for row in rows if row.get("employee_id")})
        users = list(
            get_users_collection().find(
                {"_id": {"$in": [ObjectId(item) for item in employee_ids if ObjectId.is_valid(item)]}, "organisation": org},
                {"full_name": 1, "email": 1},
            )
        )
        user_by_id = {str(item.get("_id")): item for item in users}

        employees = []
        for employee_id in employee_ids:
            assignments = [int(row.get("connection_id")) for row in rows if str(row.get("employee_id")) == employee_id]
            profile = user_by_id.get(employee_id, {})
            employees.append(
                {
                    "employee_id": employee_id,
                    "full_name": str(profile.get("full_name") or ""),
                    "email": str(profile.get("email") or ""),
                    "connection_ids": sorted(assignments),
                }
            )

        return {
            "response_type": "info",
            "message": f"Access details available for {len(employees)} employee(s).",
            "data": {"employees": employees},
            "next_steps": ["Use 'remove access from employee' or 'give access to employee ...' to update permissions."],
        }

    def _admin_view_metadata(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user_query
        return self._list_tables(user=user, entities=entities, user_query=user_query)

    def _admin_view_logs(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = entities
        _ = user_query
        org = self._org(user)
        employee_ids = [str(item.get("_id")) for item in get_users_collection().find({"organisation": org}, {"_id": 1})]
        rows = list(query_logs_collection().find({"employee_id": {"$in": employee_ids}}).sort("created_at", -1).limit(50))
        logs = [
            {
                "id": str(row.get("_id")),
                "employee_id": row.get("employee_id"),
                "user_prompt": row.get("user_prompt", ""),
                "execution_time": row.get("execution_time", 0),
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]
        return {
            "response_type": "info",
            "message": f"Loaded {len(logs)} query log item(s).",
            "data": {"logs": logs},
            "next_steps": ["Use logs for operational audit only, not for data analytics responses."],
        }

    def _employee_list_connections(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = entities
        _ = user_query
        org = self._org(user)

        permission_rows = list(permissions_collection().find({"employee_id": user.id, "organisation": org, "can_read": True}))
        allowed_ids = [int(item.get("connection_id")) for item in permission_rows]
        if not allowed_ids:
            return {
                "response_type": "info",
                "message": "No assigned connections found.",
                "data": {"connections": []},
                "next_steps": ["Request access from your admin."],
            }

        rows = list(connections_collection().find({"organisation": org, "connection_id": {"$in": allowed_ids}}).sort("connection_id", 1))
        names = [
            str(row.get("database_name") or row.get("name") or f"connection-{row.get('connection_id')}").strip()
            for row in rows
        ]
        preview = ", ".join([name for name in names if name][:5])
        summary = f"You have {len(rows)} assigned connection(s)."
        if preview:
            summary = f"{summary} Assigned databases: {preview}."
        if len(names) > 5:
            summary = f"{summary} (+{len(names) - 5} more)"
        return {
            "response_type": "info",
            "message": summary,
            "data": {"connections": [serialize_connection(row) for row in rows]},
            "next_steps": ["Use 'view schema' to understand available tables and columns."],
        }

    def _employee_view_schema(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user_query
        return self._list_tables(user=user, entities=entities, user_query=user_query)

    def _list_tables(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        rows, _connections, scope = self._get_metadata_rows_with_scope(user=user, entities=entities, user_query=user_query)
        table_names = sorted(
            {
                normalize_table_name(str(row.get("table_name") or ""))
                for row in rows
                if normalize_table_name(str(row.get("table_name") or ""))
            }
        )

        if not table_names:
            return {
                "response_type": "info",
                "message": "No tables found in this database.",
                "data": {"tables": [], "database_scope": scope},
                "next_steps": ["Check connection setup or ask admin to refresh metadata."],
            }

        return {
            "response_type": "info",
            "message": f"You have {len(table_names)} tables in this database.",
            "data": {"tables": table_names, "database_scope": scope},
            "next_steps": [
                "Describe a table (e.g., 'describe students')",
                "Ask for columns (e.g., 'columns in students')",
            ],
        }

    def _describe_table(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        table_name = normalize_table_name(str(entities.get("table_name") or ""))
        if not table_name:
            raise ValueError("Table name is required. Example: describe students")

        rows, _connections, scope = self._get_metadata_rows_with_scope(user=user, entities=entities, user_query=user_query)
        columns = [
            {
                "column_name": str(row.get("column_name") or "").strip(),
                "data_type": str(row.get("data_type") or "").strip(),
            }
            for row in rows
            if normalize_table_name(str(row.get("table_name") or "")) == table_name and str(row.get("column_name") or "").strip()
        ]

        if not columns:
            raise ValueError(f"Table '{table_name}' was not found in your accessible metadata")

        return {
            "response_type": "info",
            "message": f"Table '{table_name}' has {len(columns)} columns.",
            "data": {"table": table_name, "columns": columns, "database_scope": scope},
            "next_steps": [
                "Ask for another table (e.g., 'describe orders')",
                "Use SQL assistant for data analysis on this table.",
            ],
        }

    def _list_columns(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        return self._describe_table(user=user, entities=entities, user_query=user_query)

    def _db_key(self, name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (name or "").strip().lower())

    def _infer_database_name_from_query(self, user_query: str, connection_by_id: dict[int, dict[str, Any]]) -> tuple[str | None, str | None]:
        query = (user_query or "").strip().lower()
        if not query:
            return None, None

        db_name_by_key: dict[str, str] = {}
        connection_name_to_db_name: dict[str, str] = {}
        for row in connection_by_id.values():
            db_name = str(row.get("database_name") or "").strip().lower()
            connection_name = str(row.get("name") or "").strip().lower()
            if db_name:
                db_name_by_key[self._db_key(db_name)] = db_name
                db_key_no_suffix = re.sub(r"(?:database|db)$", "", self._db_key(db_name))
                if db_key_no_suffix:
                    db_name_by_key[db_key_no_suffix] = db_name
            if db_name and connection_name:
                connection_key = self._db_key(connection_name)
                if connection_key:
                    connection_name_to_db_name[connection_key] = db_name
                    connection_key_no_suffix = re.sub(r"(?:database|db)$", "", connection_key)
                    if connection_key_no_suffix:
                        connection_name_to_db_name[connection_key_no_suffix] = db_name

        if not db_name_by_key and not connection_name_to_db_name:
            return None, None

        stop_words = {
            "the",
            "a",
            "an",
            "my",
            "this",
            "that",
            "table",
            "tables",
            "schema",
            "metadata",
            "particular",
            "perticular",
        }

        patterns = [
            re.compile(r"\b(?:database|db)\s*(?:name)?\s*[:=]?\s*([a-zA-Z_][a-zA-Z0-9_-]*)\b", re.IGNORECASE),
            re.compile(r"\b(?:in|for|from)\s+([a-zA-Z_][a-zA-Z0-9_-]*)\b", re.IGNORECASE),
        ]

        requested_name: str | None = None

        for pattern in patterns:
            for match in pattern.finditer(query):
                candidate = (match.group(1) or "").strip().lower().strip(".,!?;:()[]{}\"'")
                if not candidate or candidate in stop_words:
                    continue

                if requested_name is None:
                    requested_name = candidate

                candidate_key = self._db_key(candidate)
                if candidate_key in db_name_by_key:
                    return db_name_by_key[candidate_key], requested_name

                if candidate_key in connection_name_to_db_name:
                    return connection_name_to_db_name[candidate_key], requested_name

                candidate_key_no_suffix = re.sub(r"(?:database|db)$", "", candidate_key)
                if candidate_key_no_suffix in db_name_by_key:
                    return db_name_by_key[candidate_key_no_suffix], requested_name
                if candidate_key_no_suffix in connection_name_to_db_name:
                    return connection_name_to_db_name[candidate_key_no_suffix], requested_name

        return None, requested_name

    def _get_metadata_rows_with_scope(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]], dict[str, Any]]:
        org = self._org(user)
        target_connection_id = entities.get("connection_id")
        target_database_name = str(entities.get("database_name") or "").strip().lower()
        requested_database_name: str | None = None
        query_lower = (user_query or "").strip().lower()
        mentions_database_scope = bool(re.search(r"\b(?:database|db)\b", query_lower))

        connection_docs = list(
            connections_collection().find(
                {"organisation": org},
                {"connection_id": 1, "name": 1, "database_name": 1},
            )
        )
        connection_by_id: dict[int, dict[str, Any]] = {
            int(item.get("connection_id")): item for item in connection_docs if item.get("connection_id") is not None
        }

        if not target_database_name:
            inferred_database_name, requested_database_name = self._infer_database_name_from_query(
                user_query=user_query,
                connection_by_id=connection_by_id,
            )
            if inferred_database_name:
                target_database_name = inferred_database_name
            elif requested_database_name:
                raise ValueError(f"Database '{requested_database_name}' was not found in your accessible scope")

        if user.role == "admin":
            allowed_ids = list(connection_by_id.keys())
            table_scope_by_connection: dict[int, tuple[bool, set[str]]] = {connection_id: (True, set()) for connection_id in allowed_ids}
        else:
            permission_rows = list(
                permissions_collection().find(
                    {"employee_id": user.id, "organisation": org, "can_read": True},
                    {"connection_id": 1, "allowed_tables": 1},
                )
            )
            if not permission_rows:
                raise ValueError("You do not have schema access permissions")

            allowed_ids = [
                int(item.get("connection_id"))
                for item in permission_rows
                if int(item.get("connection_id")) in connection_by_id
            ]
            table_scope_by_connection = {
                int(item.get("connection_id")): normalize_allowed_tables(item.get("allowed_tables", ["*"]))
                for item in permission_rows
                if int(item.get("connection_id")) in connection_by_id
            }

        if mentions_database_scope and not target_database_name and target_connection_id is None:
            accessible_db_names = sorted(
                {
                    str((connection_by_id.get(connection_id) or {}).get("database_name") or "").strip().lower()
                    for connection_id in allowed_ids
                    if str((connection_by_id.get(connection_id) or {}).get("database_name") or "").strip()
                }
            )
            if accessible_db_names:
                preview = ", ".join(accessible_db_names[:8])
                raise ValueError(
                    f"Please specify a database name. Available databases in your scope: {preview}."
                )
            raise ValueError("Please specify a database name for this request.")

        if target_connection_id is not None:
            if int(target_connection_id) not in allowed_ids:
                raise ValueError("No access to selected connection")
            allowed_ids = [int(target_connection_id)]

        if target_database_name:
            allowed_ids = [
                connection_id
                for connection_id in allowed_ids
                if str((connection_by_id.get(connection_id) or {}).get("database_name") or "").strip().lower() == target_database_name
            ]
            if not allowed_ids:
                raise ValueError(f"Database '{target_database_name}' was not found in your accessible scope")

        if not allowed_ids:
            return [], connection_by_id, {
                "database": target_database_name or None,
                "requested_database": requested_database_name,
                "connection_ids": [],
            }

        rows = list(
            metadata_collection()
            .find(
                {"connection_id": {"$in": allowed_ids}},
                {"connection_id": 1, "table_name": 1, "column_name": 1, "data_type": 1},
            )
            .sort([("connection_id", 1), ("table_name", 1), ("column_name", 1)])
            .limit(5000)
        )

        filtered_rows: list[dict[str, Any]] = []
        for row in rows:
            connection_id = int(row.get("connection_id"))
            all_tables, allowed_set = table_scope_by_connection.get(connection_id, (True, set()))
            table_name = normalize_table_name(str(row.get("table_name") or ""))
            if all_tables or table_name in allowed_set:
                filtered_rows.append(row)

        scope = {
            "database": target_database_name or None,
            "requested_database": requested_database_name,
            "connection_ids": sorted({int(connection_id) for connection_id in allowed_ids}),
        }
        return filtered_rows, connection_by_id, scope

    def _employee_permission_issue(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = entities
        _ = user_query
        org = self._org(user)
        rows = list(permissions_collection().find({"employee_id": user.id, "organisation": org}))
        if not rows:
            return {
                "response_type": "error",
                "message": "You currently have no assigned permissions.",
                "data": {},
                "next_steps": [
                    "Ask your admin to assign permissions for a connection.",
                    "Request can_read to view schema and can_query/can_export as needed.",
                ],
            }

        summary = [
            {
                "connection_id": int(row.get("connection_id")),
                "can_read": bool(row.get("can_read", False)),
                "can_query": bool(row.get("can_query", False)),
                "can_visualize": bool(row.get("can_visualize", False)),
                "can_export": bool(row.get("can_export", False)),
                "allowed_tables": row.get("allowed_tables", ["*"]),
            }
            for row in rows
        ]
        return {
            "response_type": "error",
            "message": "Permission issue detected. Access is restricted for one or more resources.",
            "data": {"permissions": summary},
            "next_steps": ["If access is still blocked, request can_read/can_query for the target connection."],
        }

    def _employee_request_access(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = entities
        _ = user_query
        return {
            "response_type": "action",
            "message": "Access request prepared. Please contact your admin with the connection and required access level.",
            "data": {},
            "next_steps": [
                "Request: can_read for target connection",
                "Request: can_query if you need analytics queries",
                "Request: can_export if you need downloads",
            ],
        }

    def _employee_help(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user
        _ = entities
        _ = user_query
        return {
            "response_type": "info",
            "message": "System assistant can help with operations, metadata, permissions, and navigation.",
            "data": {
                "supported_employee_intents": [
                    "employee_list_connections",
                    "employee_view_schema",
                    "employee_permission_issue",
                    "employee_help",
                    "employee_export_request",
                ],
                "navigation": {
                    "sql_bot": "Use SQL assistant for any data retrieval, aggregation, or trend questions.",
                    "system_assistant": "Use this assistant for access, setup, metadata, and control operations.",
                },
            },
            "next_steps": [
                "Try: 'list my connections'",
                "Try: 'show tables'",
                "Try: 'export this as csv'",
            ],
        }

    def _greeting(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user
        _ = entities
        _ = user_query
        return {
            "response_type": "info",
            "message": "Hi! I can help you manage employees, connections, and explore your database schema. What would you like to do?",
            "data": {},
            "next_steps": ["Show employees", "Show tables", "Add connection"],
        }

    def _small_talk(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user
        _ = entities
        _ = user_query
        return {
            "response_type": "info",
            "message": "I'm here to help with your system tasks. What would you like to do?",
            "data": {},
            "next_steps": ["Show employees", "List tables", "Show connections"],
        }

    def _help_general(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user
        _ = entities
        _ = user_query
        return {
            "response_type": "info",
            "message": "You can manage employees, connections, permissions, and explore database schema. For data analysis, I will redirect you to the query assistant.",
            "data": {},
            "next_steps": ["Show employees", "List tables", "Describe a table"],
        }

    def _capability_query(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user
        _ = entities
        _ = user_query
        return {
            "response_type": "info",
            "message": "This system assistant handles operations, permissions, and schema guidance. It does not run analytics queries and redirects data analysis to the SQL assistant.",
            "data": {},
            "next_steps": ["Show tables", "Describe students table", "Show my connections"],
        }

    def _org_info(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = entities
        _ = user_query
        org = self._org(user)
        return {
            "response_type": "info",
            "message": f"You are in organisation '{org}'.",
            "data": {
                "organisation": org,
                "role": (user.role or "").strip().lower(),
                "email": (user.email or "").strip().lower(),
                "user_id": user.id,
            },
            "next_steps": ["Show my connections", "Show tables", "Describe a table"],
        }

    def _clarification_needed(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user
        _ = entities
        _ = user_query
        return {
            "response_type": "error",
            "message": "I need more details. You can ask about employees, connections, or tables.",
            "data": {},
            "next_steps": ["Show employees", "Show tables"],
        }

    def _follow_up(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user
        _ = entities
        _ = user_query
        return {
            "response_type": "info",
            "message": "Next, you can continue with employees, connections, or schema details.",
            "data": {},
            "next_steps": ["Show employees", "Show tables", "Describe a table"],
        }

    def _security_blocked(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        _ = user
        _ = entities
        _ = user_query
        return {
            "response_type": "error",
            "message": "This request is blocked by system safety and access policies.",
            "data": {},
            "next_steps": ["Use approved system commands like 'show tables' or 'show employees'."],
        }

    def _employee_export_request(self, user: UserDoc, entities: dict[str, Any], user_query: str) -> dict[str, Any]:
        lower_query = (user_query or "").strip().lower()
        org = self._org(user)
        fmt = (entities.get("export_format") or "csv").strip().lower()
        if fmt not in {"csv", "excel", "pdf"}:
            raise ValueError("Unsupported export format. Use csv, excel, or pdf")

        previous_context_id = str(entities.get("previous_context_id") or "").strip()
        refers_previous = any(token in lower_query for token in {"export this", "download this", "this as", "that as"})
        if refers_previous and not previous_context_id:
            raise ValueError(
                "Export requires previous SQL bot context. Provide result_id=<id> from the last SQL assistant response."
            )

        export_rows = list(
            permissions_collection().find(
                {"employee_id": user.id, "organisation": org, "can_export": True},
                {"connection_id": 1},
            )
        )
        if not export_rows:
            raise ValueError("Export permission is not assigned for your account")

        # The assistant does not read query result data. It only prepares a safe export trigger.
        return {
            "response_type": "action",
            "message": "Export request prepared. Triggering export API is allowed for your role.",
            "data": {
                "api_call": {
                    "method": "POST",
                    "endpoint": f"/api/v1/employee/analyse/export/{fmt}",
                    "payload_contract": {
                        "result_id": previous_context_id,
                        "prompt": "<last_sql_bot_prompt>",
                        "connection_ids": [int(item.get("connection_id")) for item in export_rows],
                        "mode": "analytics",
                    },
                }
            },
            "next_steps": [
                "Provide the last SQL assistant prompt/context id in frontend state.",
                "Call the provided endpoint to download the file.",
            ],
        }

    def _resolve_employee(self, org: str, entities: dict[str, Any]) -> dict[str, Any] | None:
        employee_id = (entities.get("employee_id") or "").strip()
        email = (entities.get("email") or "").strip().lower()

        users_coll = get_users_collection()
        if employee_id:
            try:
                return users_coll.find_one({"_id": ObjectId(employee_id), "role": "employee", "organisation": org})
            except Exception:
                return None
        if email:
            return users_coll.find_one({"email": email, "role": "employee", "organisation": org})
        return None

    def _generate_temp_password(self) -> str:
        alphabet = string.ascii_letters + string.digits
        core = "".join(secrets.choice(alphabet) for _ in range(10))
        return f"Aa#{core}"
