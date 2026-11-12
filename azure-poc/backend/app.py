"""Mock legacy loans backend for the Azure POC (synthetic data only)."""
from __future__ import annotations

import copy
import hmac
import importlib.util
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from jwt import PyJWKClient
from pydantic import BaseModel, Field


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


_auth = _load_sibling("auth")
AuthError = _auth.AuthError
EntraManagedIdentityVerifier = _auth.EntraManagedIdentityVerifier

SEED = {
    "loans": {
        "L-1001": {
            "status": "active", "balance": 25000.0, "late_fee": 150.0, "deferrals": [],
            "income": {"verified": False, "monthly_income": None}, "inquiry_count": 0,
            "payments": [
                {"date": "2026-07-01", "amount": 500.0},
                {"date": "2026-08-01", "amount": 500.0},
                {"date": "2026-09-01", "amount": 500.0},
            ],
        },
        "L-1002": {
            "status": "active", "balance": 8200.0, "late_fee": 0.0, "deferrals": [],
            "income": {"verified": True, "monthly_income": 4200}, "inquiry_count": 0,
            "payments": [{"date": "2026-09-01", "amount": 300.0}],
        },
    },
    "audit": [],
}


class Deferral(BaseModel):
    months: int = Field(ge=1, le=3)


class Waiver(BaseModel):
    amount: float = Field(gt=0)


class IncomeVerification(BaseModel):
    verified: bool
    monthly_income: float


def create_app() -> FastAPI:
    """Create an independently configured backend application."""
    tenant_id = os.environ.get("TENANT_ID", "")
    backend_client_id = os.environ.get("BACKEND_CLIENT_ID", "")
    apim_mi_object_id = os.environ.get("APIM_MI_OBJECT_ID", "")
    admin_key = os.environ.get("ADMIN_KEY", "")
    auth_mode = os.environ.get("BACKEND_AUTH_MODE", "entra_mi")
    jwks = PyJWKClient(
        f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys", cache_keys=True
    )
    verifier = EntraManagedIdentityVerifier(
        tenant_id,
        backend_client_id,
        apim_mi_object_id,
        key_resolver=lambda token: jwks.get_signing_key_from_jwt(token).key,
    )
    lock = threading.Lock()
    state = copy.deepcopy(SEED)
    app = FastAPI(title="Loans backend (legacy, POC)", version="0.1.0")

    def authenticate(authorization: str | None = Header(default=None)) -> str:
        if auth_mode == "none":
            return "unauthenticated"
        try:
            return verifier.verify(authorization)
        except AuthError as error:
            raise HTTPException(status_code=error.status, detail=error.code)

    def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
        if not admin_key or not x_admin_key or not hmac.compare_digest(x_admin_key, admin_key):
            raise HTTPException(status_code=401, detail="admin_key_required")

    def loan(loan_id: str) -> dict:
        result = state["loans"].get(loan_id)
        if result is None:
            raise HTTPException(status_code=404, detail="loan_not_found")
        return result

    def audit(op: str, loan_id: str, caller: str) -> None:
        state["audit"].append(
            {"ts": datetime.now(timezone.utc).isoformat(), "op": op, "loan_id": loan_id, "caller": caller}
        )

    @app.get("/loans/{loan_id}", operation_id="get_loan_details")
    def get_loan_details(loan_id: str, caller: str = Depends(authenticate)):
        with lock:
            result = loan(loan_id)
            return {key: value for key, value in result.items() if key != "payments"} | {"loan_id": loan_id}

    @app.get("/loans/{loan_id}/payments", operation_id="get_payment_history")
    def get_payment_history(loan_id: str, caller: str = Depends(authenticate)):
        with lock:
            return {"loan_id": loan_id, "payments": loan(loan_id)["payments"]}

    @app.get("/loans/{loan_id}/credit-report", operation_id="get_credit_report")
    def get_credit_report(loan_id: str, caller: str = Depends(authenticate)):
        with lock:
            result = loan(loan_id)
            result["inquiry_count"] += 1
            audit("credit_report", loan_id, caller)
            return {"loan_id": loan_id, "score": 710, "inquiries": result["inquiry_count"]}

    @app.post("/loans/{loan_id}/deferrals", status_code=201, operation_id="create_payment_deferral")
    def create_payment_deferral(loan_id: str, body: Deferral, caller: str = Depends(authenticate)):
        with lock:
            result = loan(loan_id)
            result["deferrals"].append({"months": body.months})
            audit("deferral", loan_id, caller)
            return {"loan_id": loan_id, "deferrals": result["deferrals"]}

    @app.post("/loans/{loan_id}/late-fee-waivers", operation_id="waive_late_fee")
    def waive_late_fee(loan_id: str, body: Waiver, caller: str = Depends(authenticate)):
        with lock:
            result = loan(loan_id)
            if body.amount > result["late_fee"]:
                raise HTTPException(status_code=422, detail="amount_exceeds_late_fee")
            result["late_fee"] -= body.amount
            audit("late_fee_waiver", loan_id, caller)
            return {"loan_id": loan_id, "late_fee": result["late_fee"]}

    @app.post("/loans/{loan_id}/income-verification", operation_id="update_income_verification")
    def update_income_verification(
        loan_id: str, body: IncomeVerification, caller: str = Depends(authenticate)
    ):
        with lock:
            result = loan(loan_id)
            result["income"] = {"verified": body.verified, "monthly_income": body.monthly_income}
            audit("income_verification", loan_id, caller)
            return {"loan_id": loan_id, "income": result["income"]}

    @app.delete("/loans/{loan_id}", status_code=204, include_in_schema=False)
    def delete_loan(loan_id: str, caller: str = Depends(authenticate)):
        with lock:
            loan(loan_id)
            del state["loans"][loan_id]
            audit("delete_loan", loan_id, caller)

    @app.post("/_admin/reset", include_in_schema=False, dependencies=[Depends(require_admin)])
    def admin_reset():
        nonlocal state
        with lock:
            state = copy.deepcopy(SEED)
        return {"reset": True}

    @app.get("/_debug/state", include_in_schema=False, dependencies=[Depends(require_admin)])
    def debug_state():
        with lock:
            return JSONResponse(state)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"ok": True, "auth_mode": auth_mode}

    return app


# Keep the deployment entry point compatible with ``uvicorn app:app``.
app = create_app()
