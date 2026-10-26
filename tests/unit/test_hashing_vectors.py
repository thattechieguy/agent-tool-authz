import json
from pathlib import Path

from agent_authz_bench.tokens.hashing import request_hash


def test_hashing_vectors() -> None:
    vectors = json.loads(Path("specs/test-vectors/request-hash.json").read_text(encoding="utf-8"))
    for vector in vectors["vectors"]:
        assert (
            request_hash(
                vector["method"],
                vector["path"],
                vector.get("query"),
                vector.get("body"),
                vector["run_id"],
            )
            == vector["expected_hash"]
        ), vector["description"]
