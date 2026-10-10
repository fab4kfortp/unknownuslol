"""Test helpers for protected API endpoints."""

from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app


def authenticated_client() -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/auth/register",
        json={"email": f"test-{uuid4().hex}@example.com", "password": "test-password-123"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    client.headers.update({
        "Authorization": f"Bearer {body['access_token']}",
        "X-Session-ID": body["session_id"],
    })
    return client
