"""Catalog loading helpers."""

from pathlib import Path
from typing import Any

import jsonschema
import yaml

from agent_authz_bench.catalog.models import ToolCatalog


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file as a dictionary."""
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must parse to an object")
    return data


def load_schema(path: Path) -> dict[str, Any]:
    """Load a JSON schema file."""
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must parse to an object")
    return data


def load_catalog(path: Path, schema_path: Path) -> ToolCatalog:
    """Load and validate a catalog from disk."""
    raw = load_yaml(path)
    schema = load_schema(schema_path)
    jsonschema.validate(raw, schema)
    return ToolCatalog.model_validate(raw)
