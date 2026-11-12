"""Approval store: approvals bound to the exact request, single use, time limited.

Pure logic (no web framework). In production this is a human-in-the-loop service with an
authenticated approver UI and a shared durable store. Here: in-memory, single instance.
"""
from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable


def request_hash(method: str, path: str, query: str, body: str, run_id: str) -> str:
    """sha256 over METHOD, path, query (no leading '?'), RAW body text, run id.

    The body is hashed exactly as sent (no JSON canonicalization). The agent must send the
    same bytes it submitted for approval.
    """
    parts = [method.upper(), path, query.lstrip("?"), body, run_id]
    return "sha256:" + hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


@dataclass
class Record:
    req_hash: str
    run_id: str
    approver: str
    expires_at: float
    consumed: bool = False


class VerifyError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ApprovalStore:
    def __init__(self, ttl_seconds: int = 300, clock: Callable[[], float] = time.time) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._records: dict[str, Record] = {}

    def create(self, method, path, query, body, run_id, approver) -> tuple[str, str, float]:
        approval_id = uuid.uuid4().hex
        h = request_hash(method, path, query, body, run_id)
        exp = self._clock() + self._ttl
        with self._lock:
            self._records[approval_id] = Record(h, run_id, approver, exp)
        return approval_id, h, exp

    def verify_and_consume(self, approval_id, method, path, query, body, run_id) -> str:
        """Return the approver on success. The approval is consumed only after all checks pass."""
        with self._lock:
            rec = self._records.get(approval_id)
            if rec is None or rec.run_id != run_id:
                raise VerifyError("approval_invalid")
            if self._clock() > rec.expires_at:
                raise VerifyError("approval_expired")
            if rec.req_hash != request_hash(method, path, query, body, run_id):
                raise VerifyError("approval_mismatch")
            if rec.consumed:
                raise VerifyError("approval_replayed")
            rec.consumed = True
            return rec.approver
