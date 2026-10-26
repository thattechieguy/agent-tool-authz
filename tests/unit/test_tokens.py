from pathlib import Path

import jwt
import pytest

from agent_authz_bench.tokens.keys import generate_test_keys
from agent_authz_bench.tokens.testidp import issue_access_token, issue_approval, issue_run_context


@pytest.fixture(autouse=True)
def _ensure_keys() -> None:
    generate_test_keys(Path(".keys"))


def test_access_token_claims() -> None:
    token = issue_access_token("alice", ["Loans.Read", "Loans.Credit"])
    claims = jwt.decode(
        token,
        key=(Path(".keys") / "idp.public.pem").read_bytes(),
        algorithms=["RS256"],
        audience="api://loans-gateway",
        issuer="https://idp.agent-authz-bench.test",
    )
    assert claims["sub"] == "alice"
    assert claims["scp"] == "Loans.Read Loans.Credit"
    assert "SeniorServicer" in claims["roles"]


def test_expired_access_token_rejected() -> None:
    token = issue_access_token("alice", ["Loans.Read"], expired=True)
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(
            token,
            key=(Path(".keys") / "idp.public.pem").read_bytes(),
            algorithms=["RS256"],
            audience="api://loans-gateway",
            issuer="https://idp.agent-authz-bench.test",
        )


def test_wrong_key_rejected() -> None:
    token = issue_access_token("alice", ["Loans.Read"], signing_key="attacker")
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(
            token,
            key=(Path(".keys") / "idp.public.pem").read_bytes(),
            algorithms=["RS256"],
            audience="api://loans-gateway",
            issuer="https://idp.agent-authz-bench.test",
        )


def test_run_context_and_approval_claims() -> None:
    ctx = issue_run_context(
        "run-abc", tainted=True, sources=[{"type": "upload", "id": "statement.pdf"}]
    )
    ctx_claims = jwt.decode(
        ctx,
        key=(Path(".keys") / "orchestrator.public.pem").read_bytes(),
        algorithms=["RS256"],
        audience="loans-gateway",
        issuer="orchestrator",
    )
    assert ctx_claims["run_id"] == "run-abc"
    assert ctx_claims["untrusted_content"] is True

    token, jti = issue_approval("run-abc", "sha256:abc")
    appr_claims = jwt.decode(
        token,
        key=(Path(".keys") / "approval.public.pem").read_bytes(),
        algorithms=["RS256"],
        audience="loans-gateway",
        issuer="approval-service",
    )
    assert appr_claims["req_hash"] == "sha256:abc"
    assert appr_claims["jti"] == jti
