"""Azure Function token broker skeleton for least-privilege downscoping."""

from __future__ import annotations

import json
import os
from typing import Any

import azure.functions as func
from azure.identity import ManagedIdentityCredential

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


def _require_shared_secret(req: func.HttpRequest) -> bool:
    expected = os.getenv("BROKER_SHARED_SECRET", "")
    if not expected:
        return True
    return req.headers.get("x-broker-secret", "") == expected


def _pick_role(required_roles: list[str], caller_roles: list[str]) -> str:
    caller_set = set(caller_roles)
    for role in required_roles:
        if role in caller_set:
            return role
    raise ValueError("caller lacks required role")


def _mint_entra_token(required_scope: str) -> str:
    audience = os.getenv("BROKER_RESOURCE_APP_ID_URI")
    if not audience:
        raise RuntimeError("BROKER_RESOURCE_APP_ID_URI is required")
    scope = f"{audience}/.default"
    _ = required_scope
    credential = ManagedIdentityCredential(
        client_id=os.getenv("BROKER_MANAGED_IDENTITY_CLIENT_ID") or None
    )
    token = credential.get_token(scope)
    return token.token


@app.route(route="downscope", methods=["POST"])
def downscope(req: func.HttpRequest) -> func.HttpResponse:
    """Issue a least-privileged backend token from caller + operation context."""
    if not _require_shared_secret(req):
        return func.HttpResponse(
            json.dumps({"error": "unauthorized_broker_client"}),
            status_code=401,
            mimetype="application/json",
        )
    try:
        payload = req.get_json()
        caller = payload["caller"]
        operation = payload["operation"]
        required_scope = str(operation["required_scope"])
        required_roles = [str(item) for item in operation["required_roles"]]
        caller_roles = [str(item) for item in caller["roles"]]
        role = _pick_role(required_roles, caller_roles)
        access_token = _mint_entra_token(required_scope)
    except (ValueError, KeyError, TypeError, RuntimeError) as exc:
        return func.HttpResponse(
            json.dumps({"error": "downscope_failed", "message": str(exc)}),
            status_code=403,
            mimetype="application/json",
        )

    response: dict[str, Any] = {
        "access_token": access_token,
        "token_type": "Bearer",
        "scope": required_scope,
        "role": role,
    }
    return func.HttpResponse(json.dumps(response), status_code=200, mimetype="application/json")
