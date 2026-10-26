"""Token providers for scenario runner."""

import json
import subprocess
from typing import Any, Protocol

from agent_authz_bench.config.env import UserInputConfig, load_user_input_config


class TokenProvider(Protocol):
    """Runner token provider interface."""

    def access_token(self, identity: dict[str, Any]) -> str:
        """Issue access token."""

    def run_context(self, run_id: str, ctx: dict[str, Any] | str | None) -> str | None:
        """Issue run-context token or return None."""

    def approval(self, run_id: str, req_hash: str) -> tuple[str, str]:
        """Issue approval token."""


class EnvTokenProvider:
    """Provider backed by user-supplied values in .env."""

    def __init__(self, config: UserInputConfig | None = None) -> None:
        self._config = config or load_user_input_config()

    def access_token(self, identity: dict[str, Any]) -> str:  # noqa: ARG002
        if self._config.static_access_token:
            return self._config.static_access_token
        command = ["az", "account", "get-access-token", "--output", "json"]
        if self._config.token_scope:
            command.extend(["--scope", self._config.token_scope])
        elif self._config.token_resource:
            command.extend(["--resource", self._config.token_resource])
        completed = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
        payload = json.loads(completed.stdout)
        token = payload.get("accessToken")
        if not token:
            raise RuntimeError("Azure CLI did not return an access token.")
        return str(token)

    def run_context(self, run_id: str, ctx: dict[str, Any] | str | None) -> str | None:  # noqa: ARG002
        if ctx == "omit":
            return None
        if self._config.static_run_context_token:
            return self._config.static_run_context_token
        raise NotImplementedError(
            "Set AAB_RUN_CONTEXT_TOKEN in .env for gateways that require run-context tokens."
        )

    def approval(self, run_id: str, req_hash: str) -> tuple[str, str]:  # noqa: ARG002
        if self._config.static_approval_token:
            return self._config.static_approval_token, "user-provided"
        raise NotImplementedError(
            "Set AAB_APPROVAL_TOKEN in .env for scenarios that require approval tokens."
        )


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
