"""HTTP helpers: call APIM like an agent would, ask the approval service, inspect backend state."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests

from . import orchestrator
from .config import get_config

TIMEOUT = 40


def request_hash(method: str, path: str, query: str, body: str, run_id: str) -> str:
    """Must match approval-service/logic.py exactly (parity is unit tested)."""
    parts = [method.upper(), path, query.lstrip("?"), body, run_id]
    return "sha256:" + hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


@dataclass
class Resp:
    status: int
    text: str
    headers: dict = field(default_factory=dict)
    approval_id: str | None = None

    @property
    def json(self) -> Any:
        try:
            return json.loads(self.text)
        except ValueError:
            return None

    @property
    def error(self) -> str | None:
        j = self.json
        if isinstance(j, dict):
            return j.get("error") or j.get("detail")
        return None


def _dump(body: Any) -> str:
    return json.dumps(body, separators=(",", ":"))


def create_approval(method: str, path: str, body_str: str, run_id: str, query: str = "") -> str:
    cfg = get_config()
    r = requests.post(
        f"{cfg.approval_url}/approvals",
        headers={"X-Approver-Key": cfg.approver_key},
        json={"method": method, "path": path, "query": query, "body": body_str,
              "run_id": run_id, "approver": "supervisor-1"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["approval_id"]


def call(session, scopes, method, path, *, run_id, body=None, node="node-1",
         context="untainted", approval=None, headers=None, token=None, send_token=True) -> Resp:
    """One agent tool call through APIM.

    context : "untainted" | "tainted" | "omit" | "forged"
    approval: None | "bind" (approve this exact request) | ("bind_body", other_body)
              | ("reuse", approval_id)
    token   : override the bearer token (e.g. garbage); send_token=False sends none.
    """
    cfg = get_config()
    url = cfg.apim_base + path
    body_str = "" if body is None else _dump(body)
    h = {"X-Agent-Run-Id": run_id, "X-Agent-Node-Id": node}
    if body is not None:
        h["Content-Type"] = "application/json"
    if send_token:
        tok = token if token is not None else session.token(scopes)
        h["Authorization"] = f"Bearer {tok}"

    if context == "untainted":
        h["X-Run-Context"] = orchestrator.run_context(run_id, tainted=False)
    elif context == "tainted":
        h["X-Run-Context"] = orchestrator.run_context(
            run_id, tainted=True, sources=["upload:statement.pdf"])
    elif context == "forged":
        h["X-Run-Context"] = orchestrator.forged_run_context(run_id)
    elif context != "omit":
        raise ValueError(f"unknown context {context!r}")

    approval_id = None
    if approval is not None:
        url_path = urlparse(url).path  # the path APIM sees (includes the API suffix)
        if approval == "bind":
            approval_id = create_approval(method, url_path, body_str, run_id)
        elif approval[0] == "bind_body":
            approval_id = create_approval(method, url_path, _dump(approval[1]), run_id)
        elif approval[0] == "reuse":
            approval_id = approval[1]
        else:
            raise ValueError(f"unknown approval {approval!r}")
        h["X-Approval-Id"] = approval_id

    if headers:
        h.update(headers)
    r = requests.request(method, url, headers=h,
                         data=body_str.encode("utf-8") if body is not None else None,
                         timeout=TIMEOUT)
    return Resp(r.status_code, r.text, dict(r.headers), approval_id)


# ---- direct backend access (tests only) --------------------------------------------------
def backend_direct(method: str, path: str, token: str, body: Any = None) -> Resp:
    cfg = get_config()
    r = requests.request(
        method, cfg.backend_url + path,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=None if body is None else _dump(body).encode("utf-8"), timeout=TIMEOUT)
    return Resp(r.status_code, r.text, dict(r.headers))


def admin_reset() -> None:
    cfg = get_config()
    r = requests.post(f"{cfg.backend_url}/_admin/reset",
                      headers={"X-Admin-Key": cfg.admin_key}, timeout=TIMEOUT)
    r.raise_for_status()


def state() -> dict:
    cfg = get_config()
    r = requests.get(f"{cfg.backend_url}/_debug/state",
                     headers={"X-Admin-Key": cfg.admin_key}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()
