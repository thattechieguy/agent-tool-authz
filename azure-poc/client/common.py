"""Assertion and request helpers. Keys are read only from the local .env file."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

import jwt


def load_env() -> None:
    path = Path(".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def canonical_request_hash(method: str, url_or_path: str, body: bytes | str | None, run_id: str, sub: str, azp: str, node_id: str) -> str:
    parsed = urlsplit(url_or_path)
    path = parsed.path or "/"
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    raw_body = body.encode() if isinstance(body, str) else (body or b"")
    payload = b"\n".join([method.upper().encode(), path.encode(), query.encode(), raw_body, run_id.encode(), sub.encode(), azp.encode(), node_id.encode()])
    return hashlib.sha256(payload).hexdigest()


def signed_run_context(sub: str, azp: str, run_id: str, node_id: str, tainted: bool) -> str:
    load_env()
    encoded_key = os.environ.get("ORCHESTRATOR_SIGNING_KEY_B64")
    audience = os.environ.get("GATEWAY_CLIENT_ID")
    if not encoded_key or not audience:
        raise RuntimeError("ORCHESTRATOR_SIGNING_KEY_B64 and GATEWAY_CLIENT_ID are required")
    now = int(time.time())
    return jwt.encode(
        {"iss": "aap-poc-orchestrator", "aud": f"api://{audience}", "sub": sub, "azp": azp,
         "run_id": run_id, "node_id": node_id, "tainted": tainted, "iat": now, "exp": now + 300, "jti": str(uuid.uuid4())},
        base64.b64decode(encoded_key), algorithm="HS256",
    )


def redacted_claims(token: str) -> dict[str, object]:
    claims = jwt.decode(token, options={"verify_signature": False})
    return {key: claims.get(key) for key in ("scp", "roles", "aud", "azp", "ver", "oid", "sub") if key in claims}


def json_bytes(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
