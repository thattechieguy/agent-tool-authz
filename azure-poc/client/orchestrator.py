"""Stands in for the agent orchestrator: signs the run-context (taint) claim."""
from __future__ import annotations

import base64
import os
import time

import jwt


def run_context(run_id: str, tainted: bool, sources: list[str] | None = None,
                key_b64: str | None = None, expires_in: int = 600) -> str:
    """HS256 token the APIM policy validates with the orchestrator-signing-key named value."""
    if key_b64 is None:
        from .config import get_config
        key_b64 = get_config().orchestrator_key_b64
    now = int(time.time())
    payload = {
        "iss": "orchestrator",
        "aud": "loans-gateway",
        "run_id": run_id,
        "untrusted_content": tainted,
        "sources": sources or [],
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, base64.b64decode(key_b64), algorithm="HS256",
                      headers={"typ": "run-context+jwt"})


def forged_run_context(run_id: str, tainted: bool = False) -> str:
    """Same claims, signed with a key the gateway does not know."""
    return run_context(run_id, tainted, key_b64=base64.b64encode(os.urandom(32)).decode())
