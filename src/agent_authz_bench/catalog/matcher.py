"""Catalog route matching helpers."""

import re
from dataclasses import dataclass
from urllib.parse import unquote

from agent_authz_bench.catalog.models import ToolCatalog

_PARAM_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_RUN_PATH_PATTERN = re.compile(r"%2e|%2f|%5c", re.IGNORECASE)


@dataclass(frozen=True)
class MatchResult:
    """Catalog match result."""

    tool_id: str
    normalized_path: str


def normalize_path(path: str) -> str | None:
    """Normalize and validate a request path."""
    if not path.startswith("/"):
        return None
    if path != "/" and path.endswith("/"):
        return None
    if "//" in path:
        return None
    if "\\" in path:
        return None
    if _RUN_PATH_PATTERN.search(path):
        return None

    if path == "/":
        return path

    segments = path[1:].split("/")
    if any(seg in {"", ".", ".."} for seg in segments):
        return None
    for segment in segments:
        decoded = unquote(segment)
        if decoded in {".", ".."}:
            return None

    return path


def template_to_regex(path_template: str) -> re.Pattern[str]:
    """Convert a path template to a strict regex."""
    result = "^"
    pos = 0
    seen_params: set[str] = set()
    for match in _PARAM_PATTERN.finditer(path_template):
        result += re.escape(path_template[pos : match.start()])
        param = match.group(1)
        if param in seen_params:
            raise ValueError(f"duplicate parameter '{param}' in path template")
        seen_params.add(param)
        result += r"([A-Za-z0-9_-]+)"
        pos = match.end()
    result += re.escape(path_template[pos:])
    result += "$"

    if path_template.count("{") != path_template.count("}"):
        raise ValueError("unbalanced braces in path template")

    return re.compile(result)


def match_tool(catalog: ToolCatalog, method: str, raw_path: str) -> MatchResult | None:
    """Find matching tool and normalized path."""
    normalized = normalize_path(raw_path)
    if normalized is None:
        return None

    method_u = method.upper()
    for tool in catalog.tools:
        if tool.operation.method != method_u:
            continue
        if template_to_regex(tool.operation.path).match(normalized):
            return MatchResult(tool_id=tool.id, normalized_path=normalized)
    return None
