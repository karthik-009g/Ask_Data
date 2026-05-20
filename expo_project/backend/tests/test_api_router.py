import pytest

from app.services.system_assistant.api_router import SystemApiRouter


@pytest.mark.parametrize(
    "intent,query",
    [
        ("admin_list_employees", "list employees"),
        ("admin_list_connections", "list connections"),
        ("admin_view_metadata", "show metadata"),
        ("admin_view_logs", "show logs"),
    ],
)
def test_admin_routing_success(fake_db, userdoc_factory, admin_user, intent, query):
    router = SystemApiRouter()
    user = userdoc_factory(admin_user)

    result = router.route_intent(intent=intent, user=user, entities={}, user_query=query)

    assert result["response_type"] in {"action", "info"}
    assert isinstance(result["data"], dict)


def test_employee_unassigned_connection_blocked(fake_db, userdoc_factory, employee_user):
    router = SystemApiRouter()
    user = userdoc_factory(employee_user)

    with pytest.raises(ValueError):
        router.route_intent(
            intent="employee_view_schema",
            user=user,
            entities={"connection_id": 99},
            user_query="show schema connection 99",
        )


def test_organisation_isolation_in_list_connections(fake_db, userdoc_factory, employee_user):
    router = SystemApiRouter()
    user = userdoc_factory(employee_user)

    result = router.route_intent(
        intent="employee_list_connections",
        user=user,
        entities={},
        user_query="list my connections",
    )

    connections = result["data"]["connections"]
    assert len(connections) == 1
    assert connections[0]["id"] == 1


def test_admin_employee_list_is_org_isolated(fake_db, userdoc_factory, admin_user):
    router = SystemApiRouter()
    user = userdoc_factory(admin_user)

    result = router.route_intent(
        intent="admin_list_employees",
        user=user,
        entities={},
        user_query="list employees",
    )

    emails = [item["email"] for item in result["data"]["employees"]]
    assert "employee@acme.com" in emails
    assert "other@globex.com" not in emails


def test_export_request_requires_previous_context(fake_db, userdoc_factory, employee_user):
    router = SystemApiRouter()
    user = userdoc_factory(employee_user)

    with pytest.raises(ValueError):
        router.route_intent(
            intent="employee_export_request",
            user=user,
            entities={"export_format": "csv"},
            user_query="export this as csv",
        )


def test_export_request_has_expected_endpoint(fake_db, userdoc_factory, employee_user):
    router = SystemApiRouter()
    user = userdoc_factory(employee_user)

    result = router.route_intent(
        intent="employee_export_request",
        user=user,
        entities={"export_format": "csv", "previous_context_id": "ctx_123"},
        user_query="export this as csv result_id=ctx_123",
    )

    assert result["response_type"] == "action"
    assert result["data"]["api_call"]["method"] == "POST"
    assert result["data"]["api_call"]["endpoint"] == "/api/v1/employee/analyse/export/csv"
    assert result["data"]["api_call"]["payload_contract"]["result_id"] == "ctx_123"


def test_create_employee_missing_email(fake_db, userdoc_factory, admin_user):
    router = SystemApiRouter()
    user = userdoc_factory(admin_user)

    with pytest.raises(ValueError):
        router.route_intent(
            intent="admin_create_employee",
            user=user,
            entities={},
            user_query="add employee",
        )


def test_admin_assign_permission_requires_connection(fake_db, userdoc_factory, admin_user):
    router = SystemApiRouter()
    user = userdoc_factory(admin_user)

    with pytest.raises(ValueError):
        router.route_intent(
            intent="admin_assign_permission",
            user=user,
            entities={"email": "employee@acme.com"},
            user_query="assign permission to employee",
        )


def test_route_intent_dispatches_to_correct_handler(fake_db, userdoc_factory, admin_user, monkeypatch):
    router = SystemApiRouter()
    user = userdoc_factory(admin_user)

    called = {"name": ""}

    def _fake_handler(user, entities, user_query):
        _ = user
        _ = entities
        _ = user_query
        called["name"] = "admin_view_metadata"
        return {"response_type": "info", "message": "ok", "data": {}, "next_steps": []}

    monkeypatch.setattr(router, "_admin_view_metadata", _fake_handler)
    result = router.route_intent("admin_view_metadata", user, {}, "show metadata")

    assert called["name"] == "admin_view_metadata"
    assert result["message"] == "ok"


@pytest.mark.parametrize(
    "intent,handler_name",
    [
        ("admin_list_employees", "_admin_list_employees"),
        ("admin_create_employee", "_admin_create_employee"),
        ("admin_delete_employee", "_admin_delete_employee"),
        ("admin_list_connections", "_admin_list_connections"),
        ("admin_create_connection", "_admin_create_connection"),
        ("admin_update_connection", "_admin_update_connection"),
        ("admin_delete_connection", "_admin_delete_connection"),
        ("admin_assign_permission", "_admin_assign_permission"),
        ("admin_view_metadata", "_admin_view_metadata"),
        ("admin_view_logs", "_admin_view_logs"),
        ("employee_list_connections", "_employee_list_connections"),
        ("employee_view_schema", "_employee_view_schema"),
        ("employee_permission_issue", "_employee_permission_issue"),
        ("employee_help", "_employee_help"),
        ("employee_export_request", "_employee_export_request"),
    ],
)
def test_all_intent_handler_mappings(fake_db, userdoc_factory, admin_user, monkeypatch, intent, handler_name):
    router = SystemApiRouter()
    user = userdoc_factory(admin_user)
    state = {"handler": None}

    def _fake_handler(user, entities, user_query):
        _ = user
        _ = entities
        _ = user_query
        state["handler"] = handler_name
        return {"response_type": "info", "message": "ok", "data": {}, "next_steps": []}

    monkeypatch.setattr(router, handler_name, _fake_handler)
    result = router.route_intent(intent=intent, user=user, entities={}, user_query="noop")

    assert state["handler"] == handler_name
    assert result["message"] == "ok"


def test_list_tables_scoped_to_database_name_in_query(fake_db, userdoc_factory, admin_user):
    router = SystemApiRouter()
    user = userdoc_factory(admin_user)

    fake_db.connections.insert_one(
        {
            "connection_id": 3,
            "organisation": "acme",
            "name": "acme-warehouse",
            "db_type": "postgresql",
            "host": "localhost",
            "port": 5432,
            "username": "user",
            "database_name": "clg_database",
            "connection_url": None,
            "is_active": True,
        }
    )
    fake_db.metadata.insert_one(
        {
            "connection_id": 3,
            "table_name": "attendance",
            "column_name": "id",
            "data_type": "integer",
        }
    )

    result = router.route_intent(
        intent="list_tables",
        user=user,
        entities={},
        user_query="give tables in clg_database",
    )

    assert result["response_type"] == "info"
    assert result["data"]["tables"] == ["attendance"]
    assert result["data"]["database_scope"]["database"] == "clg_database"
    assert result["data"]["database_scope"]["requested_database"] == "clg_database"
    assert result["data"]["database_scope"]["connection_ids"] == [3]


def test_list_tables_unknown_database_in_query_raises(fake_db, userdoc_factory, admin_user):
    router = SystemApiRouter()
    user = userdoc_factory(admin_user)

    with pytest.raises(ValueError):
        router.route_intent(
            intent="list_tables",
            user=user,
            entities={},
            user_query="give tables in unknown_database",
        )


def test_list_tables_particular_database_requires_name(fake_db, userdoc_factory, admin_user):
    router = SystemApiRouter()
    user = userdoc_factory(admin_user)

    with pytest.raises(ValueError) as exc_info:
        router.route_intent(
            intent="list_tables",
            user=user,
            entities={},
            user_query="show tables in particular database",
        )

    assert "specify a database name" in str(exc_info.value).lower()


def test_list_tables_resolves_database_from_connection_name_alias(fake_db, userdoc_factory, admin_user):
    router = SystemApiRouter()
    user = userdoc_factory(admin_user)

    # Make existing connection point to a different DB so this test can isolate scope.
    for row in fake_db.connections.rows:
        if int(row.get("connection_id", 0)) == 1:
            row["database_name"] = "main"

    fake_db.connections.insert_one(
        {
            "connection_id": 3,
            "organisation": "acme",
            "name": "clg_database",
            "db_type": "postgresql",
            "host": "localhost",
            "port": 5432,
            "username": "user",
            "database_name": "clg",
            "connection_url": None,
            "is_active": True,
        }
    )
    fake_db.metadata.insert_one(
        {
            "connection_id": 3,
            "table_name": "attendance",
            "column_name": "id",
            "data_type": "integer",
        }
    )

    result = router.route_intent(
        intent="list_tables",
        user=user,
        entities={},
        user_query="i want tables only in clg_database",
    )

    assert result["response_type"] == "info"
    assert result["data"]["tables"] == ["attendance"]
    assert result["data"]["database_scope"]["database"] == "clg"
    assert result["data"]["database_scope"]["connection_ids"] == [3]


def test_employee_list_tables_in_database_returns_only_assigned_tables(fake_db, userdoc_factory, employee_user):
    router = SystemApiRouter()
    user = userdoc_factory(employee_user)

    # Same connection has both assigned and unassigned tables; employee is assigned only "customers".
    fake_db.metadata.insert_one(
        {
            "connection_id": 1,
            "table_name": "orders",
            "column_name": "order_id",
            "data_type": "integer",
        }
    )

    result = router.route_intent(
        intent="list_tables",
        user=user,
        entities={},
        user_query="what are the tables assigned to me in clg database",
    )

    assert result["response_type"] == "info"
    assert result["data"]["tables"] == ["customers"]
    assert result["data"]["database_scope"]["database"] == "clg"
