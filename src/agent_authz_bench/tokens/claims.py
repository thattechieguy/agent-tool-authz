"""Claim parsing helpers."""

from pathlib import Path
from typing import Any

import jwt


def decode_rs256_token(
    token: str,
    *,
    key_path: Path,
    audience: str,
    issuer: str,
) -> dict[str, Any]:
    """Decode and validate an RS256 JWT."""
    key = key_path.read_bytes()
    return jwt.decode(token, key=key, algorithms=["RS256"], audience=audience, issuer=issuer)
