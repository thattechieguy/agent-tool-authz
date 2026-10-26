import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from agent_authz_bench.backend.app import create_backend_app
from agent_authz_bench.tokens.keys import generate_test_keys


def _service_token() -> str:
    secret = (Path(".keys") / "backend_service_secret.txt").read_text(encoding="utf-8").strip()
    return jwt.encode(
        {"iss": "gateway", "aud": "loans-backend", "sub": "svc-gateway"}, secret, algorithm="HS256"
    )


@pytest.fixture
def client() -> TestClient:
    generate_test_keys(Path(".keys"))
    os.environ["BACKEND_AUTH_MODE"] = "service_token"
    os.environ["ADMIN_KEY"] = "test-admin-key"
    return TestClient(create_backend_app())


def test_admin_and_debug_require_key(client: TestClient) -> None:
    assert client.get("/_debug/state").status_code == 401
    assert client.post("/_admin/reset").status_code == 401
    assert client.get("/_debug/state", headers={"X-Admin-Key": "test-admin-key"}).status_code == 200


def test_service_token_required(client: TestClient) -> None:
    assert client.get("/loans/L-1001").status_code == 401
    assert (
        client.get(
            "/loans/L-1001", headers={"Authorization": f"Bearer {_service_token()}"}
        ).status_code
        == 200
    )


def test_credit_report_increments_inquiry_and_audit(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {_service_token()}"}
    first = client.get("/loans/L-1001/credit-report", headers=headers)
    second = client.get("/loans/L-1001/credit-report", headers=headers)
    assert first.status_code == 200
    assert second.json()["inquiries"] == 2
    state = client.get("/_debug/state", headers={"X-Admin-Key": "test-admin-key"}).json()
    assert len(state["audit"]) == 2
    assert state["audit"][0]["caller"] == "svc-gateway"


def test_mutations_and_validations(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {_service_token()}"}
    assert (
        client.post("/loans/L-1001/deferrals", headers=headers, json={"months": 2}).status_code
        == 201
    )
    assert (
        client.post("/loans/L-1001/deferrals", headers=headers, json={"months": 5}).status_code
        == 422
    )
    assert (
        client.post(
            "/loans/L-1001/late-fee-waivers", headers=headers, json={"amount": 9999}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/loans/L-1001/income-verification",
            headers=headers,
            json={"verified": True, "monthly_income": 5000},
        ).status_code
        == 200
    )


def test_none_auth_mode_uses_unauthenticated_caller() -> None:
    os.environ["BACKEND_AUTH_MODE"] = "none"
    os.environ["ADMIN_KEY"] = "test-admin-key"
    test_client = TestClient(create_backend_app())
    response = test_client.get("/loans/L-1001/credit-report")
    assert response.status_code == 200
    state = test_client.get("/_debug/state", headers={"X-Admin-Key": "test-admin-key"}).json()
    assert state["audit"][0]["caller"] == "unauthenticated"
