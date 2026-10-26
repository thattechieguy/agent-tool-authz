from pathlib import Path

from agent_authz_bench.catalog.loader import load_catalog
from agent_authz_bench.catalog.matcher import match_tool, normalize_path


def _catalog():
    return load_catalog(
        Path("catalogs/loans-servicing.catalog.yaml"), Path("schema/catalog.schema.json")
    )


def test_match_success() -> None:
    result = match_tool(_catalog(), "GET", "/loans/L-1001")
    assert result is not None
    assert result.tool_id == "get_loan_details"
    assert result.normalized_path == "/loans/L-1001"


def test_reject_dot_segments() -> None:
    assert normalize_path("/loans/../L-1001") is None
    assert normalize_path("/loans/%2e%2e/L-1001") is None


def test_reject_encoded_slashes_and_backslashes() -> None:
    assert normalize_path("/loans/%2fsecret") is None
    assert normalize_path("/loans/%5csecret") is None
    assert normalize_path("/loans\\L-1001") is None


def test_reject_empty_segments() -> None:
    assert normalize_path("/loans//L-1001") is None


def test_reject_trailing_slash() -> None:
    assert normalize_path("/loans/L-1001/") is None
    assert normalize_path("/") == "/"


def test_no_match_for_unknown_operation() -> None:
    assert match_tool(_catalog(), "DELETE", "/loans/L-1001") is None
