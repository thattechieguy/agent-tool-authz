"""Settings from environment variables or a local .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALL_SCOPES = ["Loans.Read", "Loans.Credit", "Loans.Deferral", "Loans.Waiver", "Loans.Income"]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _req(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"Missing setting {name}. Copy .env.example to .env and fill it in.")
    return value


@dataclass(frozen=True)
class Config:
    tenant_id: str
    agent_client_id: str
    gateway_client_id: str
    apim_base: str
    backend_url: str
    approval_url: str
    admin_key: str
    approver_key: str
    orchestrator_key_b64: str
    users: dict


@lru_cache(maxsize=1)
def get_config() -> Config:
    _load_dotenv(ROOT / ".env")
    return Config(
        tenant_id=_req("TENANT_ID"),
        agent_client_id=_req("AGENT_CLIENT_ID"),
        gateway_client_id=_req("GATEWAY_CLIENT_ID"),
        apim_base=_req("APIM_BASE").rstrip("/"),
        backend_url=_req("BACKEND_URL").rstrip("/"),
        approval_url=_req("APPROVAL_URL").rstrip("/"),
        admin_key=_req("ADMIN_KEY"),
        approver_key=_req("APPROVER_KEY"),
        orchestrator_key_b64=_req("ORCHESTRATOR_SIGNING_KEY_B64"),
        users={
            "alice": _req("USER_ALICE"),
            "bob": _req("USER_BOB"),
            "dave": _req("USER_DAVE"),
        },
    )
