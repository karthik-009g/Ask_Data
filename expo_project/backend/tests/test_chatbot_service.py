from app.services.system_assistant.chatbot_service import SystemAssistantChatbotService


def test_redirect_for_data_queries(userdoc_factory, admin_user, monkeypatch):
    service = SystemAssistantChatbotService()
    user = userdoc_factory(admin_user)

    result = service.handle_chat(
        user_query="total sales last month",
        user_role="admin",
        user_org="acme",
        user=user,
    )

    assert result["type"] == "redirect"
    assert result["data"]["target"] == "SQL_BOT"


def test_org_scope_mismatch_returns_error(userdoc_factory, admin_user):
    service = SystemAssistantChatbotService()
    user = userdoc_factory(admin_user)

    result = service.handle_chat(
        user_query="list employees",
        user_role="admin",
        user_org="globex",
        user=user,
    )

    assert result["type"] == "error"
    assert "Organisation scope mismatch" in result["message"]


def test_role_denied_message(userdoc_factory, employee_user):
    service = SystemAssistantChatbotService()
    user = userdoc_factory(employee_user)

    result = service.handle_chat(
        user_query="list employees",
        user_role="employee",
        user_org="acme",
        user=user,
    )

    assert result["type"] == "error"
    assert "allowed" in result["message"].lower() or "permission" in result["message"].lower()


def test_missing_entities_validation_error(userdoc_factory, admin_user, monkeypatch):
    service = SystemAssistantChatbotService()
    user = userdoc_factory(admin_user)

    # Ensure intent is create employee, but with no extracted email.
    monkeypatch.setattr(
        "app.services.system_assistant.chatbot_service.classify_intent",
        lambda user_query, user_role, entities: "admin_create_employee",
    )

    result = service.handle_chat(
        user_query="add employee",
        user_role="admin",
        user_org="acme",
        user=user,
    )

    assert result["type"] == "error"
    assert "required" in result["message"].lower()


def test_invalid_intent_safe_error(userdoc_factory, admin_user, monkeypatch):
    service = SystemAssistantChatbotService()
    user = userdoc_factory(admin_user)

    monkeypatch.setattr(
        "app.services.system_assistant.chatbot_service.classify_intent",
        lambda user_query, user_role, entities: "unknown_intent",
    )

    result = service.handle_chat(
        user_query="do something unknown",
        user_role="admin",
        user_org="acme",
        user=user,
    )

    assert result["type"] == "error"
    assert "not allowed" in result["message"].lower() or "unsupported" in result["message"].lower()
