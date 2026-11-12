"""Request a manual approval only after an explicit local confirmation."""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path

import httpx

from .common import canonical_request_hash, json_bytes, load_env


def main() -> None:
    if len(sys.argv) != 9:
        raise SystemExit("usage: python -m client.approve <method> <path> <json_body> <run_id> <sub> <azp> <node_id> <operation_id>")
    method, path, body, run_id, sub, azp, node_id, operation_id = sys.argv[1:]
    load_env()
    approval_url, approver_key = os.getenv("APPROVAL_SERVICE_URL"), os.getenv("APPROVER_KEY")
    if not approval_url or not approver_key:
        raise SystemExit("APPROVAL_SERVICE_URL and APPROVER_KEY are required in .env")
    request_hash = canonical_request_hash(method, path, json_bytes(json.loads(body)), run_id, sub, azp, node_id)
    print(f"Manual approval requested: {operation_id} {method} {path}, run={run_id}, hash={request_hash}")
    if input("Type APPROVE to issue this approval: ") != "APPROVE":
        raise SystemExit("approval not issued")
    response = httpx.post(
        f"{approval_url.rstrip('/')}/issue",
        headers={"X-Approver-Key": approver_key},
        json={"sub": sub, "azp": azp, "run_id": run_id, "node_id": node_id, "operation_id": operation_id, "request_hash": request_hash},
        timeout=10,
    )
    response.raise_for_status()
    output = Path(".token_cache") / f"approval-{run_id}.jwt"
    output.parent.mkdir(exist_ok=True)
    output.write_text(response.json()["approval"], encoding="utf-8")
    print(f"Approval issued and stored at {output}; the assertion was not printed.")


if __name__ == "__main__":
    main()
