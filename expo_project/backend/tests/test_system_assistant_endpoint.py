from fastapi.testclient import TestClient


def _build_client(monkeypatch, current_user):
    from app.core import dependencies
    from app.main import app

    monkeypatch.setattr("app.main.ensure_super_admin_user", lambda: None)
    app.dependency_overrides[dependencies.get_current_user] = lambda: current_user
    return TestClient(app)


def test_endpoint_redirect_for_data_query(monkeypatch, userdoc_factory, employee_user):
    user = userdoc_factory(employee_user)
    client = _build_client(monkeypatch, user)

    response = client.post("/api/v1/system-assistant/chat", json={"user_query": "top customers"})

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "redirect"
    assert body["data"]["target"] == "SQL_BOT"


def test_endpoint_admin_only_role_guard(monkeypatch, userdoc_factory):
    from app.db.mongo import UserDoc

    user = UserDoc(
        {
            "_id": "64b64b64b64b64b64b64b650",
            "email": "super@acme.com",
            "full_name": "Super",
            "role": "super_admin",
            "organisation": "",
        }
    )
    client = _build_client(monkeypatch, user)

    response = client.post("/api/v1/system-assistant/chat", json={"user_query": "list employees"})

    assert response.status_code == 403


def test_endpoint_calls_service(monkeypatch, userdoc_factory, admin_user):
    user = userdoc_factory(admin_user)
    client = _build_client(monkeypatch, user)

    monkeypatch.setattr(
        "app.api.v1.system_assistant.system_assistant_service.handle_chat",
        lambda user_query, user_role, user_org, user: {
            "type": "info",
            "message": "ok",
            "data": {"intent": "employee_help"},
            "next_steps": [],
        },
    )

    response = client.post("/api/v1/system-assistant/chat", json={"user_query": "help"})

    assert response.status_code == 200
    assert response.json()["message"] == "ok"
