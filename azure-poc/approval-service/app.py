"""Approval service for the Azure POC."""
from __future__ import annotations

import base64
import hmac
import importlib.util
import os
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel


def _load_sibling(name: str):
    module_name = f"{__name__}._{name}"
    if module := sys.modules.get(module_name):
        return module
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(f"{name}.py"))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load sibling module {name!r}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_logic = _load_sibling("logic")
ApprovalStore = _logic.ApprovalStore
VerifyError = _logic.VerifyError


class RequestDesc(BaseModel):
    method: str
    path: str
    query: str = ""
    body: str = ""
    run_id: str


class CreateApproval(RequestDesc):
    approver: str = "supervisor-1"


class VerifyApproval(RequestDesc):
    approval_id: str


class ApprovalFacts(BaseModel):
    sub: str
    azp: str
    run_id: str
    node_id: str
    operation_id: str
    request_hash: str


class ConsumeApproval(ApprovalFacts):
    approval: str


def create_app() -> FastAPI:
    """Create an approval service using configuration present at this call."""
    approver_key = os.environ.get("APPROVER_KEY", "")
    verify_key = os.environ.get("VERIFY_KEY", "")
    gateway_client_id = os.environ.get("GATEWAY_CLIENT_ID", "")
    ttl_seconds = int(os.environ.get("APPROVAL_TTL_SECONDS", "300"))
    store = ApprovalStore(ttl_seconds=ttl_seconds)
    used_approvals: set[str] = set()
    used_approvals_lock = threading.Lock()
    app = FastAPI(title="Approval service (POC)", version="0.1.0")

    def check(expected: str, supplied: str | None) -> None:
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.post("/approvals")
    def create_approval(req: CreateApproval, x_approver_key: str | None = Header(default=None)):
        check(approver_key, x_approver_key)
        approval_id, request_digest, expires_at = store.create(
            req.method, req.path, req.query, req.body, req.run_id, req.approver
        )
        return {"approval_id": approval_id, "req_hash": request_digest, "expires_at": expires_at}

    @app.post("/verify")
    def verify(req: VerifyApproval, x_verify_key: str | None = Header(default=None)):
        check(verify_key, x_verify_key)
        try:
            approver = store.verify_and_consume(
                req.approval_id, req.method, req.path, req.query, req.body, req.run_id
            )
        except VerifyError as error:
            return JSONResponse(status_code=403, content={"error": error.code})
        return {"valid": True, "approver": approver}

    @app.post("/issue")
    def issue(req: ApprovalFacts, x_approver_key: str | None = Header(default=None)):
        check(approver_key, x_approver_key)
        try:
            signing_key = base64.b64decode(verify_key, validate=True)
        except ValueError:
            raise HTTPException(status_code=500, detail="approval_misconfigured")
        now = datetime.now(timezone.utc)
        approval = jwt.encode(
            req.model_dump() | {
                "iss": "approval-service",
                "aud": gateway_client_id,
                "iat": now,
                "exp": now + timedelta(seconds=ttl_seconds),
                "jti": uuid.uuid4().hex,
            },
            signing_key,
            algorithm="HS256",
        )
        return {"approval": approval}

    @app.post("/verify-and-consume")
    def verify_and_consume(req: ConsumeApproval):
        try:
            signing_key = base64.b64decode(verify_key, validate=True)
            claims = jwt.decode(
                req.approval,
                signing_key,
                algorithms=["HS256"],
                audience=gateway_client_id,
                issuer="approval-service",
                options={"require": ["exp", "iat", "jti"]},
            )
        except (ValueError, jwt.PyJWTError):
            return JSONResponse(status_code=403, content={"error": "approval_invalid"})
        if any(claims.get(field) != getattr(req, field) for field in ApprovalFacts.model_fields):
            return JSONResponse(status_code=403, content={"error": "approval_mismatch"})
        approval_id = claims["jti"]
        with used_approvals_lock:
            if approval_id in used_approvals:
                return JSONResponse(status_code=403, content={"error": "approval_replayed"})
            used_approvals.add(approval_id)
        return {"valid": True}

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app


# Keep the deployment entry point compatible with ``uvicorn app:app``.
app = create_app()
