"""Audit helpers."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write_audit(log_path: str, payload: dict[str, Any]) -> None:
    """Write one audit line to stdout and audit file."""
    record = {"ts": datetime.now(tz=UTC).isoformat(), **payload}
    line = json.dumps(record, ensure_ascii=False)
    print(line)  # noqa: T201
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
