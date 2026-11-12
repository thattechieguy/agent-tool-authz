"""Exactly seven offline scaffold contract tests."""

from __future__ import annotations

import base64
import importlib.util
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[2]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


client_common = load("poc_client_common", ROOT / "client" / "common.py")
backend = load("poc_backend", ROOT / "backend" / "app.py")
approval = load("poc_approval", ROOT / "approval-service" / "app.py")


def test_canonical_hash_is_stable_and_query_canonicalized():
    assert client_common.canonical_request_hash("post", "/x?b=2&a=1", b"{}", "r", "s", "a", "n") == client_common.canonical_request_hash("POST", "/x?a=1&b=2", b"{}", "r", "s", "a", "n")


def test_signed_run_context_has_required_bindings(monkeypatch):
    monkeypatch.setenv("GATEWAY_CLIENT_ID", "gateway")
    monkeypatch.setenv("ORCHESTRATOR_SIGNING_KEY_B64", base64.b64encode(b"x" * 32).decode())
    token = client_common.signed_run_context("subject", "client", "run", "node", True)
    claims = client_common.jwt.decode(token, b"x" * 32, algorithms=["HS256"], audience="api://gateway")
    assert (claims["sub"], claims["azp"], claims["run_id"], claims["node_id"], claims["tainted"]) == ("subject", "client", "run", "node", True)


def test_approval_requires_approver_credential(monkeypatch):
    monkeypatch.setenv("GATEWAY_CLIENT_ID", "gateway")
    monkeypatch.setenv("VERIFY_KEY", base64.b64encode(b"k" * 32).decode())
    monkeypatch.setenv("APPROVER_KEY", "local-test-approver")
    response = TestClient(approval.create_app()).post("/issue", json={"sub": "s", "azp": "a", "run_id": "r", "node_id": "n", "operation_id": "op", "request_hash": "h"})
    assert response.status_code == 401


def test_approval_consumption_rejects_replay(monkeypatch):
    monkeypatch.setenv("GATEWAY_CLIENT_ID", "gateway")
    monkeypatch.setenv("VERIFY_KEY", base64.b64encode(b"k" * 32).decode())
    monkeypatch.setenv("APPROVER_KEY", "local-test-approver")
    app = TestClient(approval.create_app())
    facts = {"sub": "s", "azp": "a", "run_id": "r", "node_id": "n", "operation_id": "op", "request_hash": "h"}
    issued = app.post("/issue", headers={"X-Approver-Key": "local-test-approver"}, json=facts).json()["approval"]
    assert app.post("/verify-and-consume", json=facts | {"approval": issued}).status_code == 200
    assert app.post("/verify-and-consume", json=facts | {"approval": issued}).status_code == 403


def test_backend_none_allows_synthetic_request(monkeypatch):
    monkeypatch.setenv("BACKEND_AUTH_MODE", "none")
    assert TestClient(backend.create_app()).get("/loans/L-1001").status_code == 200


def test_backend_service_endpoints_and_reset_are_not_public(monkeypatch):
    monkeypatch.setenv("BACKEND_AUTH_MODE", "none")
    monkeypatch.setenv("ADMIN_KEY", "local-test-admin")
    app = TestClient(backend.create_app())
    assert app.get("/healthz").json()["auth_mode"] == "none"
    assert app.post("/_admin/reset", headers={"X-Admin-Key": "local-test-admin"}).status_code == 200
    assert "/_admin/reset" not in app.get("/openapi.json").text


def test_public_openapi_has_six_operations_and_no_delete(monkeypatch):
    monkeypatch.setenv("BACKEND_AUTH_MODE", "none")
    schema = TestClient(backend.create_app()).get("/openapi.json").json()
    operations = [op for path in schema["paths"].values() for method, op in path.items() if method != "parameters"]
    assert len(operations) == 6
    assert {op["operationId"] for op in operations} == {"get_loan_details", "get_payment_history", "get_credit_report", "update_income_verification", "create_payment_deferral", "waive_late_fee"}
    assert all("delete" not in path for path in schema["paths"].values())
