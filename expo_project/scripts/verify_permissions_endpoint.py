import json
import time
import urllib.request
import urllib.error

BASE_BACKEND = "http://localhost:8000/api/v1"
BASE_PROXY = "http://localhost:3000/api/proxy"
PASSWORD = "Secret123!"


def call_json(method: str, url: str, payload: dict | None = None, token: str | None = None):
    body = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url=url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            return resp.status, text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8") if exc.fp else ""
        return exc.code, text


def main():
    ts = int(time.time())
    org = f"org{ts}"
    admin_email = f"admin{ts}@test.com"
    employee_email = f"employee{ts}@test.com"

    register_payload = {
        "organisation": org,
        "email": admin_email,
        "full_name": "Admin",
        "password": PASSWORD,
        "role": "admin",
    }
    status, body = call_json("POST", f"{BASE_BACKEND}/auth/register", register_payload)
    print("REGISTER_STATUS", status)
    print("REGISTER_BODY", body)

    login_payload = {
        "organisation": org,
        "email": admin_email,
        "password": PASSWORD,
    }
    status, body = call_json("POST", f"{BASE_BACKEND}/auth/login", login_payload)
    print("LOGIN_STATUS", status)
    print("LOGIN_BODY", body)
    if status != 200:
        return

    token = json.loads(body)["access_token"]

    create_employee_payload = {
        "organisation": "ignored",
        "email": employee_email,
        "full_name": "Employee",
        "password": PASSWORD,
        "role": "employee",
    }
    status, body = call_json("POST", f"{BASE_BACKEND}/admin/employees", create_employee_payload, token)
    print("CREATE_EMPLOYEE_STATUS", status)
    print("CREATE_EMPLOYEE_BODY", body)
    if status != 200:
        return

    employee_id = json.loads(body)["id"]

    status, body = call_json(
        "GET",
        f"{BASE_PROXY}/admin/employees/{employee_id}/permissions",
        payload=None,
        token=token,
    )
    print("PROXY_PERMISSIONS_STATUS", status)
    print("PROXY_PERMISSIONS_BODY", body)


if __name__ == "__main__":
    main()
