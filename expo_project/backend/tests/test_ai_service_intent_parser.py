from app.services.ai_service import _parse_analytics_classifier_payload


def test_parse_classifier_payload_from_strict_json() -> None:
    payload = _parse_analytics_classifier_payload('{"is_analytics": false, "intent": "non-analytics", "reason": "example"}')
    assert payload is not None
    assert payload.get("is_analytics") is False


def test_parse_classifier_payload_from_markdown_block() -> None:
    content = "```json\n{\"is_analytics\": true, \"intent\": \"analytics\", \"reason\": \"metric request\"}\n```"
    payload = _parse_analytics_classifier_payload(content)
    assert payload is not None
    assert payload.get("is_analytics") is True


def test_parse_classifier_payload_from_text_label_non_analytics() -> None:
    payload = _parse_analytics_classifier_payload("Intent: non-analytics. Reason: asks for sample queries")
    assert payload is not None
    assert payload.get("is_analytics") is False


def test_parse_classifier_payload_returns_none_for_unknown_text() -> None:
    payload = _parse_analytics_classifier_payload("I am not sure")
    assert payload is None
