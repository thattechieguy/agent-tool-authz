import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from agent_authz_bench.gateway.app import create_gateway_app
from agent_authz_bench.gateway.config import GatewayConfig
from agent_authz_bench.gateway.pipeline import DecisionError, GatewayPipeline
from agent_authz_bench.tokens.hashing import request_hash
from agent_authz_bench.tokens.keys import generate_test_keys
from agent_authz_bench.tokens.testidp import issue_access_token, issue_approval, issue_run_context


def _config(mode: str = "reference") -> GatewayConfig:
    secret = (Path(".keys") / "backend_service_secret.txt").read_text(encoding="utf-8").strip()
    return GatewayConfig(mode=mode, backend_service_secret=secret)


@pytest.fixture(autouse=True)
def _keys() -> None:
    generate_test_keys(Path(".keys"))


def _headers(
    *,
    user: str = "alice",
    scopes: list[str] | None = None,
    run_id: str = "run-abc",
    include_run_ctx: bool = True,
    caller_type: str = "ai-orchestrator",
    node_id: str = "unknown",
) -> dict[str, str]:
    token = issue_access_token(
        user,
        scopes or ["Loans.Income"],
        extra_claims={"caller_type": caller_type, "node_id": node_id},
    )
    headers = {
        "authorization": f"Bearer {token}",
        "x-agent-run-id": run_id,
        "x-agent-node-id": node_id,
    }
    if include_run_ctx:
        headers["x-run-context"] = issue_run_context(run_id, tainted=False)
    return headers


def test_pipeline_step_ordering_missing_run_id_before_unknown_operation() -> None:
    pipeline = GatewayPipeline(_config())
    with pytest.raises(DecisionError) as exc:
        pipeline.authorize(
            method="DELETE",
            path="/does-not-exist",
            query={},
            body=b"",
            headers={"authorization": f"Bearer {issue_access_token('alice', ['Loans.Read'])}"},
        )
    assert exc.value.error == "missing_run_id"


def test_unauthorized_client() -> None:
    pipeline = GatewayPipeline(_config())
    token = issue_access_token(
        "alice",
        ["Loans.Read"],
        client="other-app",
        extra_claims={"caller_type": "ai-orchestrator", "node_id": "unknown"},
    )
    with pytest.raises(DecisionError) as exc:
        pipeline.authorize(
            method="GET",
            path="/loans/L-1001",
            query={},
            body=b"",
            headers={
                "authorization": f"Bearer {token}",
                "x-agent-run-id": "run-abc",
                "x-run-context": issue_run_context("run-abc", tainted=False),
            },
        )
    assert exc.value.error == "unauthorized_client"


def test_approval_required_for_tainted_income_write() -> None:
    pipeline = GatewayPipeline(_config())
    body = b'{"verified": true, "monthly_income": 9000}'
    with pytest.raises(DecisionError) as exc:
        pipeline.authorize(
            method="POST",
            path="/loans/L-1001/income-verification",
            query={},
            body=body,
            headers={
                **_headers(user="alice", scopes=["Loans.Income"]),
                "x-run-context": issue_run_context("run-abc", tainted=True),
            },
        )
    assert exc.value.error == "approval_required"


def test_approval_mismatch_and_replay() -> None:
    pipeline = GatewayPipeline(_config())
    body = b'{"verified": true, "monthly_income": 5000}'
    req_hash = request_hash(
        "POST",
        "/loans/L-1001/income-verification",
        {},
        body.decode("utf-8"),
        "run-abc",
    )
    bad_token, _ = issue_approval("run-abc", "sha256:deadbeef")
    with pytest.raises(DecisionError) as mismatch:
        pipeline.authorize(
            method="POST",
            path="/loans/L-1001/income-verification",
            query={},
            body=body,
            headers={
                **_headers(user="alice", scopes=["Loans.Income"]),
                "x-run-context": issue_run_context("run-abc", tainted=True),
                "x-approval-token": bad_token,
            },
        )
    assert mismatch.value.error == "approval_mismatch"

    token, jti = issue_approval("run-abc", req_hash)
    first = pipeline.authorize(
        method="POST",
        path="/loans/L-1001/income-verification",
        query={},
        body=body,
        headers={
            **_headers(user="alice", scopes=["Loans.Income"]),
            "x-run-context": issue_run_context("run-abc", tainted=True),
            "x-approval-token": token,
        },
    )
    assert first.approval_jti == jti
    with pytest.raises(DecisionError) as replay:
        pipeline.authorize(
            method="POST",
            path="/loans/L-1001/income-verification",
            query={},
            body=body,
            headers={
                **_headers(user="alice", scopes=["Loans.Income"]),
                "x-run-context": issue_run_context("run-abc", tainted=True),
                "x-approval-token": token,
            },
        )
    assert replay.value.error == "approval_replayed"


def test_weak_mode_allows_and_mints_service_token() -> None:
    pipeline = GatewayPipeline(_config(mode="weak"))
    result = pipeline.authorize(
        method="DELETE",
        path="/loans/L-1001",
        query={},
        body=b"",
        headers={"authorization": f"Bearer {issue_access_token('bob', ['Loans.Read'])}"},
    )
    claims = jwt.decode(
        result.forward_headers["Authorization"].split(" ", 1)[1],
        key=(Path(".keys") / "backend_service_secret.txt").read_text(encoding="utf-8").strip(),
        algorithms=["HS256"],
        audience="loans-backend",
        issuer="gateway",
    )
    assert claims["sub"] == "svc-gateway"


def test_rejected_request_not_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    os.environ["GATEWAY_MODE"] = "reference"
    os.environ["BACKEND_URL"] = "http://127.0.0.1:9000"
    os.environ["AUDIT_LOG_PATH"] = "logs/test-audit.jsonl"
    app = create_gateway_app()

    calls: list[str] = []

    class FakeClient:
        async def __aenter__(self):  # noqa: ANN204
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            return None

        async def request(self, *args, **kwargs):  # noqa: ANN001, ANN002
            calls.append("called")
            raise AssertionError("backend should not be called")

    monkeypatch.setattr("agent_authz_bench.gateway.app.httpx.AsyncClient", lambda **_: FakeClient())
    client = TestClient(app)
    response = client.post(
        "/loans/L-1001/income-verification",
        json={"verified": True, "monthly_income": 9000},
        headers={
            "Authorization": (
                "Bearer "
                + issue_access_token(
                    "alice",
                    ["Loans.Income"],
                    extra_claims={"caller_type": "ai-orchestrator", "node_id": "unknown"},
                )
            )
        },
    )
    assert response.status_code == 400
    assert response.json()["error"] == "missing_run_id"
    assert calls == []


def test_missing_caller_type_claim_rejected() -> None:
    pipeline = GatewayPipeline(_config())
    token = issue_access_token(
        "alice", ["Loans.Read"], extra_claims={"caller_type": "", "node_id": "unknown"}
    )
    with pytest.raises(DecisionError) as exc:
        pipeline.authorize(
            method="GET",
            path="/loans/L-1001",
            query={},
            body=b"",
            headers={
                "authorization": f"Bearer {token}",
                "x-agent-run-id": "run-abc",
                "x-agent-node-id": "unknown",
                "x-run-context": issue_run_context("run-abc", tainted=False),
            },
        )
    assert exc.value.error == "invalid_caller_context"


def test_langgraph_node_policy_rejected_for_wrong_tool() -> None:
    pipeline = GatewayPipeline(_config())
    with pytest.raises(DecisionError) as exc:
        pipeline.authorize(
            method="POST",
            path="/loans/L-1001/income-verification",
            query={},
            body=b'{"verified": true, "monthly_income": 5000}',
            headers={
                **_headers(
                    user="alice",
                    scopes=["Loans.Income"],
                    caller_type="langgraph-node",
                    node_id="read-node",
                ),
                "x-run-context": issue_run_context("run-abc", tainted=False),
            },
        )
    assert exc.value.error == "insufficient_caller_policy"
