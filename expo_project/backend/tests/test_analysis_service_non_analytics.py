from app.db.mongo import UserDoc
from app.services import analysis_service


def test_non_analytics_prompt_returns_no_query(monkeypatch) -> None:
    def _should_not_run(*args, **kwargs):
        raise AssertionError("_allowed_connection_ids should not be called for non-analytics prompts")

    monkeypatch.setattr(analysis_service, "_allowed_connection_ids", _should_not_run)

    user = UserDoc(
        {
            "_id": "507f1f77bcf86cd799439011",
            "organisation": "acme",
            "role": "employee",
            "email": "employee@acme.test",
        }
    )

    result = analysis_service.execute_connection_analysis(
        user=user,
        prompt="tell me a joke about databases",
        connection_ids=[1],
        is_admin=False,
        mode="analytics",
    )

    assert result["generated_queries"] == []
    assert result["generated_sql"] == ""
    assert result["rows"] == []
    assert result["agentic"]["intent"]["no_sql_required"] is True
    assert "can't generate the query" in result["overview"].lower()
