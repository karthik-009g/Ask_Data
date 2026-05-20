from app.services.analysis_service import _is_analytics_convertible_prompt


def test_convertibility_accepts_llm_analytics_intent(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.analysis_service.classify_prompt_for_analytics",
        lambda prompt: {"is_analytics": True, "intent": "analytics"},
    )
    assert _is_analytics_convertible_prompt("give me the car id having less prize") is True


def test_convertibility_rejects_plain_greeting(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.analysis_service.classify_prompt_for_analytics",
        lambda prompt: {"is_analytics": False, "intent": "non-analytics"},
    )
    assert _is_analytics_convertible_prompt("hello") is False


def test_convertibility_rejects_non_analytics_small_talk(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.analysis_service.classify_prompt_for_analytics",
        lambda prompt: {"is_analytics": False, "intent": "non-analytics"},
    )
    assert _is_analytics_convertible_prompt("tell me a joke about cars") is False


def test_convertibility_rejects_capability_prompt(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.analysis_service.classify_prompt_for_analytics",
        lambda prompt: {"is_analytics": False, "intent": "non-analytics"},
    )
    assert _is_analytics_convertible_prompt("give me list of tasks you can perform") is False


def test_convertibility_accepts_general_data_request(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.analysis_service.classify_prompt_for_analytics",
        lambda prompt: {"is_analytics": True, "intent": "analytics"},
    )
    assert _is_analytics_convertible_prompt("show records for this table") is True


def test_convertibility_rejects_table_guidance_prompt(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.analysis_service.classify_prompt_for_analytics",
        lambda prompt: {"is_analytics": False, "intent": "non-analytics"},
    )
    prompt = (
        "You can read the following tables and help me generate some simple queries in natural language "
        "attendance cars courses customer_reviews dealerships departments distributors manufacturers "
        "reviews sales service_records wineries wines"
    )
    assert _is_analytics_convertible_prompt(prompt) is False
