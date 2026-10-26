"""Token providers for scenario runner."""

from typing import Any, Protocol

from agent_authz_bench.tokens.testidp import issue_access_token, issue_approval, issue_run_context


class TokenProvider(Protocol):
    """Runner token provider interface."""

    def access_token(self, identity: dict[str, Any]) -> str:
        """Issue access token."""

    def run_context(self, run_id: str, ctx: dict[str, Any] | str | None) -> str | None:
        """Issue run-context token or return None."""

    def approval(self, run_id: str, req_hash: str) -> tuple[str, str]:
        """Issue approval token."""


class DefaultTokenProvider:
    """Default provider backed by local test IdP helpers."""

    def access_token(self, identity: dict[str, Any]) -> str:
        return issue_access_token(
            identity["user"],
            identity["scopes"],
            client=identity.get("client", "loans-agent"),
            audience=identity.get("audience", "api://loans-gateway"),
            expired=bool(identity.get("expired", False)),
            signing_key=identity.get("signing_key", "idp"),
        )

    def run_context(self, run_id: str, ctx: dict[str, Any] | str | None) -> str | None:
        if ctx == "omit":
            return None
        if ctx == "forged":
            return issue_run_context(run_id, tainted=True, signing_key="attacker")
        if ctx is None:
            return issue_run_context(run_id, tainted=False)
        return issue_run_context(
            run_id, tainted=bool(ctx.get("tainted", False)), sources=ctx.get("sources", [])
        )

    def approval(self, run_id: str, req_hash: str) -> tuple[str, str]:
        return issue_approval(run_id, req_hash)


class EntraOboTokenProvider:
    """Stub provider showing where an Entra OBO adapter would integrate.

    A production implementation would exchange a user token using OAuth token exchange/OBO
    and mint run-context plus approval tokens from external services.
    """

    def access_token(self, identity: dict[str, Any]) -> str:  # noqa: ARG002
        raise NotImplementedError("Implement OBO token acquisition for your environment")

    def run_context(self, run_id: str, ctx: dict[str, Any] | str | None) -> str | None:  # noqa: ARG002
        raise NotImplementedError("Implement run-context token acquisition for your environment")

    def approval(self, run_id: str, req_hash: str) -> tuple[str, str]:  # noqa: ARG002
        raise NotImplementedError("Implement approval token acquisition for your environment")
