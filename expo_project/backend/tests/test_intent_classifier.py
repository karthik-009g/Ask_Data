import pytest

from app.services.system_assistant.intent_classifier import (
    DATA_QUERY_INTENT,
    classify_intent,
    detect_data_query,
    validate_role,
)


@pytest.mark.parametrize(
    "query",
    [
        "total sales last month",
        "top customers",
        "average revenue by weekly trend",
        "count users growth monthly",
        "sum profit",
    ],
)
def test_detect_data_query_true(query):
    assert detect_data_query(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "list employees",
        "create connection name=test db_type=postgresql method=form",
        "why cant i access this db",
        "help me navigate",
    ],
)
def test_detect_data_query_false(query):
    assert detect_data_query(query) is False


@pytest.mark.parametrize(
    "query,intent",
    [
        ("list employees", "admin_list_employees"),
        ("add employee john@acme.com", "admin_create_employee"),
        ("delete employee john@acme.com", "admin_delete_employee"),
        ("list connections", "admin_list_connections"),
        ("what are the databases", "admin_list_connections"),
        ("what is my organisation", "org_info"),
        ("show metadata", "admin_view_metadata"),
        ("show tables", "list_tables"),
        ("describe students table", "describe_table"),
        ("what columns are in orders", "list_columns"),
        ("show logs", "admin_view_logs"),
    ],
)
def test_classify_admin_intents(query, intent):
    assert classify_intent(query, "admin", {}) == intent


@pytest.mark.parametrize(
    "query,intent",
    [
        ("list my connections", "employee_list_connections"),
        ("what are the databases", "employee_list_connections"),
        ("what databases are given to me", "employee_list_connections"),
        ("what database are assigned to me", "employee_list_connections"),
        ("what are the databases i have", "employee_list_connections"),
        ("what is my organization", "org_info"),
        ("show schema for connection 1", "employee_view_schema"),
        ("name the tables", "list_tables"),
        ("describe orders", "describe_table"),
        ("fields in customers", "list_columns"),
        ("access denied for db", "employee_permission_issue"),
        ("help", "help_general"),
        ("export this as csv", "employee_export_request"),
    ],
)
def test_classify_employee_intents(query, intent):
    assert classify_intent(query, "employee", {}) == intent


def test_ambiguous_query_defaults_for_employee():
    assert classify_intent("what should i do now", "employee", {}) == "employee_help"


def test_ambiguous_query_defaults_for_admin():
    assert classify_intent("what should i do now", "admin", {}) == "admin_view_metadata"


def test_data_query_always_wins_over_role():
    assert classify_intent("show total sales", "admin", {}) == DATA_QUERY_INTENT
    assert classify_intent("top users", "employee", {}) == DATA_QUERY_INTENT


def test_role_validation_blocks_cross_role_intents():
    with pytest.raises(PermissionError):
        validate_role("admin_list_employees", "employee")

    with pytest.raises(PermissionError):
        validate_role("employee_help", "admin")


def test_role_validation_allows_expected():
    validate_role("admin_view_metadata", "admin")
    validate_role("employee_view_schema", "employee")
    validate_role("list_tables", "admin")
    validate_role("list_tables", "employee")


def test_llm_fallback_maps_list_connections_for_employee(monkeypatch):
    from app.services.system_assistant import intent_classifier as ic

    monkeypatch.setattr(ic, "_llm_classify_and_extract", lambda user_query, user_role, metadata_context=None: ("employee_list_connections", {"database_name": "clg_database"}))
    entities = {}
    intent = ic._llm_fallback_intent("what databases are given to me", "employee", entities)

    assert intent == "employee_list_connections"
    assert entities["database_name"] == "clg_database"
    assert entities["_intent_source"] == "llm"


def test_llm_fallback_rejects_cross_role_intent(monkeypatch):
    from app.services.system_assistant import intent_classifier as ic

    monkeypatch.setattr(ic, "_llm_classify_and_extract", lambda user_query, user_role, metadata_context=None: ("admin_list_employees", {}))
    entities = {}
    intent = ic._llm_fallback_intent("list employees", "employee", entities)

    assert intent is None


@pytest.mark.parametrize(
    "query,role,intent",
    [
        ("whata re the employyes i have", "admin", "admin_list_employees"),
        ("whata re the data bases i have", "admin", "admin_list_connections"),
        ("whata re the data bases i have", "employee", "employee_list_connections"),
    ],
)
def test_typo_variants_map_to_expected_intents(query, role, intent):
    assert classify_intent(query, role, {}) == intent
