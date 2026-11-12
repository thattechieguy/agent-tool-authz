"""Real Entra sign-in for test users, with PER-STEP scoped delegated tokens.

The user signs in once (device code). Each agent step then asks Entra for a token carrying
ONLY the scope that step needs. force_refresh=True stops MSAL from handing back an older,
broader cached token.
"""
from __future__ import annotations

import time
from pathlib import Path

import msal

from .config import ALL_SCOPES, ROOT, get_config

CACHE_DIR = ROOT / ".token_cache"


class NotLoggedIn(RuntimeError):
    pass


class UserSession:
    def __init__(self, name: str, upn: str) -> None:
        cfg = get_config()
        self.name = name
        self.upn = upn
        self.gateway_id = cfg.gateway_client_id
        CACHE_DIR.mkdir(exist_ok=True)
        self._cache_path = CACHE_DIR / f"{name}.json"
        self._cache = msal.SerializableTokenCache()
        if self._cache_path.exists():
            self._cache.deserialize(self._cache_path.read_text(encoding="utf-8"))
        self._app = msal.PublicClientApplication(
            cfg.agent_client_id,
            authority=f"https://login.microsoftonline.com/{cfg.tenant_id}",
            token_cache=self._cache,
        )
        self._mem: dict[frozenset, tuple[str, float]] = {}

    def _full(self, scopes: list[str]) -> list[str]:
        return [f"api://{self.gateway_id}/{s}" for s in scopes]

    def _save(self) -> None:
        if self._cache.has_state_changed:
            self._cache_path.write_text(self._cache.serialize(), encoding="utf-8")

    def login(self) -> None:
        """Interactive device-code sign-in. Sign in as THIS user, not as yourself."""
        flow = self._app.initiate_device_flow(scopes=self._full(ALL_SCOPES))
        if "user_code" not in flow:
            raise RuntimeError(f"Could not start device flow: {flow}")
        print(flow["message"])
        result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(result.get("error_description", str(result)))
        who = (result.get("id_token_claims") or {}).get("preferred_username", "")
        if who.lower() != self.upn.lower():
            raise RuntimeError(f"Signed in as {who!r} but expected {self.upn!r}. Try again.")
        self._save()

    def ensure_logged_in(self) -> None:
        if not self._app.get_accounts(username=self.upn):
            raise NotLoggedIn(f"{self.name} is not signed in")

    def token(self, scopes: list[str]) -> str:
        """Delegated access token carrying only `scopes` (a list like ["Loans.Read"])."""
        key = frozenset(scopes)
        hit = self._mem.get(key)
        if hit and hit[1] > time.time() + 60:
            return hit[0]
        accounts = self._app.get_accounts(username=self.upn)
        if not accounts:
            raise NotLoggedIn(f"{self.name} is not signed in")
        result = self._app.acquire_token_silent(
            self._full(scopes), account=accounts[0], force_refresh=True
        )
        if not result or "access_token" not in result:
            raise NotLoggedIn(f"Could not get a token for {self.name}: {result}")
        self._save()
        self._mem[key] = (result["access_token"], time.time() + int(result.get("expires_in", 3000)))
        return result["access_token"]
