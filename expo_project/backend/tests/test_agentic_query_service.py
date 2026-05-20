from app.db.mongo import UserDoc
from app.services import agentic_query_service
from app.services.agentic_query_service import (
    _find_reusable_cached_sql,
    _normalize_prompt_for_cache,
    _reason_for_zero_rows,
    _sql_references_metadata_table,
    _validate_sql_schema,
)


def test_validate_sql_schema_accepts_known_tables_and_columns():
    metadata_rows = [
        {"table_name": "cars", "column_name": "car_id"},
        {"table_name": "cars", "column_name": "model_name"},
        {"table_name": "customer_reviews", "column_name": "car_id"},
        {"table_name": "customer_reviews", "column_name": "rating"},
    ]
    sql = """
    SELECT c.car_id, c.model_name, AVG(cr.rating) AS avg_rating
    FROM cars c
    JOIN customer_reviews cr ON c.car_id = cr.car_id
    GROUP BY c.car_id, c.model_name
    """

    issues = _validate_sql_schema(sql, metadata_rows)

    assert issues == []


def test_validate_sql_schema_rejects_unknown_columns_and_tables():
    metadata_rows = [
        {"table_name": "cars", "column_name": "car_id"},
        {"table_name": "cars", "column_name": "model_name"},
    ]
    sql = """
    SELECT c.car_id, c.fake_col
    FROM cars c
    JOIN random_table r ON c.car_id = r.car_id
    """

    issues = _validate_sql_schema(sql, metadata_rows)

    assert any("unknown tables" in item for item in issues)
    assert any("unknown column 'c.fake_col'" in item for item in issues)


def test_reason_for_zero_rows_table_empty():
    assert _reason_for_zero_rows(0, has_where=False, has_join=False) == "table itself is empty"


def test_reason_for_zero_rows_filter_too_strict():
    assert _reason_for_zero_rows(10, has_where=True, has_join=False) == "selected filter too strict"


def test_reason_for_zero_rows_join_mismatch():
    assert _reason_for_zero_rows(10, has_where=False, has_join=True) == "table has data but no matching join rows"


def test_normalize_prompt_for_cache_collapses_spacing_and_case():
    assert _normalize_prompt_for_cache("  Show   Me   STUDENTS  ") == "show me students"


def test_sql_references_metadata_table_rejects_constant_select():
    metadata_rows = [{"table_name": "students", "column_name": "name"}]
    assert _sql_references_metadata_table("SELECT 'hello' AS msg", metadata_rows) is False


def test_sql_references_metadata_table_accepts_known_table_select():
    metadata_rows = [{"table_name": "students", "column_name": "name"}]
    assert _sql_references_metadata_table("SELECT name FROM students", metadata_rows) is True


def test_find_reusable_cached_sql_returns_matching_sql(monkeypatch):
    class _Cursor:
        def __init__(self, docs):
            self.docs = docs

        def sort(self, *_args, **_kwargs):
            return self

        def limit(self, size):
            return self.docs[:size]

    class _Collection:
        def __init__(self, docs):
            self.docs = docs

        def find(self, *_args, **_kwargs):
            return _Cursor(self.docs)

    docs = [
        {
            "user_prompt": "Show me students",
            "generated_sql": "SELECT * FROM students LIMIT 10",
        }
    ]
    monkeypatch.setattr(agentic_query_service, "query_logs_collection", lambda: _Collection(docs))

    user = UserDoc(
        {
            "_id": "507f1f77bcf86cd799439011",
            "organisation": "acme",
            "role": "employee",
            "email": "user@acme.test",
        }
    )
    connection = {"connection_id": 1}
    metadata_rows = [{"table_name": "students", "column_name": "name"}]

    sql = _find_reusable_cached_sql(
        user,
        " show   me   students ",
        connection,
        metadata_rows,
        all_tables=True,
        allowed_tables=set(),
    )

    assert sql == "SELECT * FROM students LIMIT 10"


def test_find_reusable_cached_sql_skips_constant_only_sql(monkeypatch):
    class _Cursor:
        def __init__(self, docs):
            self.docs = docs

        def sort(self, *_args, **_kwargs):
            return self

        def limit(self, size):
            return self.docs[:size]

    class _Collection:
        def __init__(self, docs):
            self.docs = docs

        def find(self, *_args, **_kwargs):
            return _Cursor(self.docs)

    docs = [{"user_prompt": "Show me students", "generated_sql": "SELECT 'task' AS item"}]
    monkeypatch.setattr(agentic_query_service, "query_logs_collection", lambda: _Collection(docs))

    user = UserDoc(
        {
            "_id": "507f1f77bcf86cd799439011",
            "organisation": "acme",
            "role": "employee",
            "email": "user@acme.test",
        }
    )
    connection = {"connection_id": 1}
    metadata_rows = [{"table_name": "students", "column_name": "name"}]

    sql = _find_reusable_cached_sql(
        user,
        "show me students",
        connection,
        metadata_rows,
        all_tables=True,
        allowed_tables=set(),
    )

    assert sql is None
