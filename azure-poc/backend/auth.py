"""Caller verification for the legacy backend.

The backend models a legacy service that trusts exactly one caller: the API Management
managed identity. It never sees the end user or the agent. Pure logic (no web framework)
so it can be unit tested without Azure.
"""
from __future__ import annotations

from typing import Callable

import jwt


class AuthError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


class EntraManagedIdentityVerifier:
    """Accepts only Entra-issued tokens for this backend whose `oid` is the APIM identity."""

    def __init__(
        self,
        tenant_id: str,
        backend_client_id: str,
        allowed_oid: str,
        key_resolver: Callable[[str], object],
    ) -> None:
        self.tenant_id = tenant_id
        self.backend_client_id = backend_client_id
        self.allowed_oid = allowed_oid
        self._key_resolver = key_resolver
        # Managed identity tokens are usually v1 (aud = App ID URI, iss = sts.windows.net).
        # Accept both v1 and v2 forms; decode a real token during setup to see which you get.
        self.audiences = [backend_client_id, f"api://{backend_client_id}"]
        self.issuers = {
            f"https://sts.windows.net/{tenant_id}/",
            f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        }

    def verify(self, authorization: str | None) -> str:
        if not (self.tenant_id and self.backend_client_id and self.allowed_oid):
            raise AuthError(500, "backend_misconfigured")
        if not authorization or not authorization.lower().startswith("bearer "):
            raise AuthError(401, "missing_token")
        token = authorization.split(" ", 1)[1].strip()
        try:
            key = self._key_resolver(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.audiences,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.PyJWTError:
            raise AuthError(401, "invalid_token")
        if claims.get("iss") not in self.issuers:
            raise AuthError(401, "invalid_token")
        if claims.get("oid") != self.allowed_oid:
            raise AuthError(403, "caller_not_allowed")
        return str(claims["oid"])
