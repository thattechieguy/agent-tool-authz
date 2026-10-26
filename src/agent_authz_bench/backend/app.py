"""Backend app module."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import jwt
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from agent_authz_bench.backend.state import BackendState


class DeferralRequest(BaseModel):
    """Request body for deferrals."""

    months: int = Field(ge=1, le=3)


class WaiverRequest(BaseModel):
    """Request body for late-fee waivers."""

    amount: float


class IncomeVerificationRequest(BaseModel):
    """Request body for income verification."""

    verified: bool
    monthly_income: float


def _load_backend_secret() -> str:
    inline = os.getenv("BACKEND_SERVICE_SECRET")
    if inline:
        return inline
    return (Path(".keys") / "backend_service_secret.txt").read_text(encoding="utf-8").strip()


def create_backend_app() -> FastAPI:
    """Create the mock backend application."""
    app = FastAPI(title="agent-authz-bench backend")
    state = BackendState()
    auth_mode = os.getenv("BACKEND_AUTH_MODE", "service_token")
    admin_key = os.getenv("ADMIN_KEY", "test-admin-key")
    backend_secret = _load_backend_secret()

    def caller_from_auth(authorization: str | None) -> str:
        if auth_mode == "none":
            return "unauthenticated"
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_service_token"
            )
        token = authorization.split(" ", 1)[1]
        try:
            claims = jwt.decode(
                token,
                key=backend_secret,
                algorithms=["HS256"],
                audience="loans-backend",
                issuer="gateway",
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_service_token"
            ) from exc
        return str(claims.get("sub", "unknown"))

    def require_admin(x_admin_key: str | None) -> None:
        if x_admin_key != admin_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_admin_key"
            )

    def get_loan_or_404(loan_id: str) -> dict[str, Any]:
        loan = state.loans.get(loan_id)
        if loan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="loan_not_found")
        return loan

    @app.post("/_admin/reset")
    def reset(
        x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    ) -> dict[str, str]:
        require_admin(x_admin_key)
        state.reset()
        return {"status": "ok"}

    @app.get("/_debug/state")
    def debug_state(
        x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    ) -> dict[str, Any]:
        require_admin(x_admin_key)
        return state.snapshot()

    @app.get("/loans/{loan_id}")
    def get_loan(loan_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        caller_from_auth(authorization)
        loan = get_loan_or_404(loan_id)
        summary = dict(loan)
        summary.pop("payments", None)
        return summary

    @app.get("/loans/{loan_id}/payments")
    def get_payments(
        loan_id: str, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        caller_from_auth(authorization)
        loan = get_loan_or_404(loan_id)
        return {"payments": loan["payments"]}

    @app.get("/loans/{loan_id}/credit-report")
    def get_credit_report(
        loan_id: str, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        caller = caller_from_auth(authorization)
        loan = get_loan_or_404(loan_id)
        loan["inquiry_count"] += 1
        state.append_audit("credit_report", loan_id, caller)
        return {"score": 710, "inquiries": loan["inquiry_count"]}

    @app.post("/loans/{loan_id}/deferrals", status_code=status.HTTP_201_CREATED)
    def create_deferral(
        loan_id: str,
        body: DeferralRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        caller = caller_from_auth(authorization)
        loan = get_loan_or_404(loan_id)
        loan["deferrals"].append({"months": body.months})
        state.append_audit("create_deferral", loan_id, caller)
        return {"status": "created"}

    @app.post("/loans/{loan_id}/late-fee-waivers")
    def waive_late_fee(
        loan_id: str,
        body: WaiverRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        caller = caller_from_auth(authorization)
        loan = get_loan_or_404(loan_id)
        if body.amount <= 0 or body.amount > loan["late_fee"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_waiver"
            )
        loan["late_fee"] -= body.amount
        state.append_audit("waive_late_fee", loan_id, caller)
        return {"late_fee": loan["late_fee"]}

    @app.post("/loans/{loan_id}/income-verification")
    def update_income_verification(
        loan_id: str,
        body: IncomeVerificationRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        caller = caller_from_auth(authorization)
        loan = get_loan_or_404(loan_id)
        loan["income"]["verified"] = body.verified
        loan["income"]["monthly_income"] = body.monthly_income
        state.append_audit("income_verification", loan_id, caller)
        return {"status": "updated"}

    @app.delete("/loans/{loan_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_loan(loan_id: str, authorization: str | None = Header(default=None)) -> None:
        caller = caller_from_auth(authorization)
        if loan_id not in state.loans:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="loan_not_found")
        del state.loans[loan_id]
        state.append_audit("delete_loan", loan_id, caller)
        return None

    return app


app = create_backend_app()
