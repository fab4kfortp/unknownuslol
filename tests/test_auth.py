from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app
from tests.auth_helpers import authenticated_client


def test_product_endpoints_require_a_valid_bearer_token():
    client = TestClient(app)
    assert client.get("/api/summary").status_code == 401
    assert client.get("/api/summary", headers={"Authorization": "Bearer invalid-token"}).status_code == 401


def test_registration_login_and_logout_lifecycle():
    client = TestClient(app)
    invalid = client.post("/api/auth/register", json={"email": "not-an-email", "password": "short"})
    assert invalid.status_code == 422

    email = f"auth-{uuid4().hex}@example.com"
    payload = {"email": email, "password": "secure-test-pass-1"}

    registered = client.post("/api/auth/register", json=payload)
    assert registered.status_code == 201
    account = registered.json()
    assert account["token_type"] == "bearer"
    assert account["session_id"]

    duplicate = client.post("/api/auth/register", json=payload)
    assert duplicate.status_code == 409

    login = client.post("/api/auth/login", json=payload)
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).json()["email"] == email

    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_accounts_cannot_request_another_accounts_session():
    first = authenticated_client()
    second = authenticated_client()
    first_session = first.headers["X-Session-ID"]

    denied = second.get(f"/api/transactions?session_id={first_session}")
    assert denied.status_code == 403

    # The legacy demo session alias is scoped to the current account, not shared.
    own_data = second.get("/api/transactions?session_id=demo")
    assert own_data.status_code == 200
