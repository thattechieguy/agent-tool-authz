"""Request hashing helpers."""

import hashlib
import json
from typing import Any
from urllib.parse import quote


def _canonical_query(query: dict[str, Any] | list[tuple[str, Any]] | None) -> str:
    if not query:
        return ""
    items: list[tuple[str, str]] = []
    if isinstance(query, dict):
        for key, value in query.items():
            if isinstance(value, list):
                for part in value:
                    items.append((str(key), str(part)))
            else:
                items.append((str(key), str(value)))
    else:
        for key, value in query:
            items.append((str(key), str(value)))
    items.sort(key=lambda item: (item[0], item[1]))
    return "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in items)


def _canonical_body(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, bytes):
        raw_text = body.decode("utf-8")
    elif isinstance(body, str):
        raw_text = body
    else:
        return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    if raw_text == "":
        return ""
    try:
        obj = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_hash(
    method: str,
    path: str,
    query: dict[str, Any] | list[tuple[str, Any]] | None,
    body: Any,
    run_id: str,
) -> str:
    """Compute canonical request hash."""
    method_u = method.upper()
    query_canonical = _canonical_query(query)
    body_canonical = _canonical_body(body)
    material = "\n".join([method_u, path, query_canonical, body_canonical, run_id])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
