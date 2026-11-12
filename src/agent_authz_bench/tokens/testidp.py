"""Synthetic test IdP helpers."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt

USERS: dict[str, list[str]] = {
    "alice": ["Servicer", "SeniorServicer"],
    "bob": ["ReadOnly"],
    "dave": ["Servicer"],
}


def _keys_dir() -> Path:
    return Path(".keys")


def _private_key(name: str) -> bytes:
    path = _keys_dir() / f"{name}.private.pem"
    return path.read_bytes()


def _now() -> datetime:
    return datetime.now(tz=UTC)


def issue_access_token(
    user: str,
    scopes: list[str],
    *,
    client: str = "loans-agent",
    audience: str = "api://loans-gateway",
    expired: bool = False,
    signing_key: str = "idp",
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Issue an RS256 access token for scenario tests."""
    now = _now()
    exp = now - timedelta(seconds=1) if expired else now + timedelta(seconds=300)
    payload: dict[str, Any] = {
        "iss": "https://idp.agent-authz-bench.test",
        "aud": audience,
        "sub": user,
        "azp": client,
        "scp": " ".join(scopes),
        "roles": USERS[user],
        "act": {"sub": "loans-agent"},
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(uuid.uuid4()),
        "caller_type": "ai-orchestrator",
        "node_id": "unknown",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        _private_key(signing_key),
        algorithm="RS256",
        headers={"typ": "at+jwt", "kid": f"{signing_key[:4]}-1"},
    )


def issue_run_context(
    run_id: str,
    *,
    tainted: bool,
    sources: list[dict[str, Any]] | None = None,
    signing_key: str = "orchestrator",
) -> str:
    """Issue an RS256 run-context token."""
    now = _now()
    payload = {
        "iss": "orchestrator",
        "aud": "loans-gateway",
        "run_id": run_id,
        "untrusted_content": tainted,
        "sources": sources or [],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=900)).timestamp()),
    }
    return jwt.encode(
        payload,
        _private_key(signing_key),
        algorithm="RS256",
        headers={"typ": "run-context+jwt", "kid": "orch-1"},
    )


def issue_approval(
    run_id: str,
    req_hash: str,
    *,
    approver: str = "supervisor-1",
    signing_key: str = "approval",
    expired: bool = False,
) -> tuple[str, str]:
    """Issue an RS256 approval token and return token plus jti."""
    now = _now()
    jti = str(uuid.uuid4())
    payload = {
        "iss": "approval-service",
        "aud": "loans-gateway",
        "run_id": run_id,
        "req_hash": req_hash,
        "approver": approver,
        "iat": int(now.timestamp()),
        "exp": int(
            (now - timedelta(seconds=1) if expired else now + timedelta(seconds=300)).timestamp()
        ),
        "jti": jti,
    }
    token = jwt.encode(
        payload,
        _private_key(signing_key),
        algorithm="RS256",
        headers={"typ": "approval+jwt", "kid": "appr-1"},
    )
    return token, jti
