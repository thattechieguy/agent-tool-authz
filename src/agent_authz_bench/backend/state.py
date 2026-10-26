"""Backend in-memory state."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

SEED_STATE: dict[str, Any] = {
    "loans": {
        "L-1001": {
            "status": "active",
            "balance": 25000.0,
            "late_fee": 150.0,
            "deferrals": [],
            "income": {"verified": False, "monthly_income": None},
            "inquiry_count": 0,
            "payments": [
                {"date": "2026-07-01", "amount": 500.0},
                {"date": "2026-08-01", "amount": 500.0},
                {"date": "2026-09-01", "amount": 500.0},
            ],
        },
        "L-1002": {
            "status": "active",
            "balance": 8200.0,
            "late_fee": 0.0,
            "deferrals": [],
            "income": {"verified": True, "monthly_income": 4200},
            "inquiry_count": 0,
            "payments": [{"date": "2026-09-01", "amount": 300.0}],
        },
    },
    "audit": [],
}


class BackendState:
    """Mutable in-memory state store."""

    def __init__(self) -> None:
        self._state: dict[str, Any] = deepcopy(SEED_STATE)

    def reset(self) -> None:
        self._state = deepcopy(SEED_STATE)

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self._state)

    @property
    def loans(self) -> dict[str, dict[str, Any]]:
        return self._state["loans"]

    def append_audit(self, op: str, loan_id: str | None, caller: str) -> None:
        self._state["audit"].append(
            {
                "ts": datetime.now(tz=UTC).isoformat(),
                "op": op,
                "loan_id": loan_id,
                "caller": caller,
            }
        )
