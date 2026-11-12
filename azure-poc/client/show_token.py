"""Decode (without verifying) a delegated token for one step, to check claims.

  python -m client.show_token alice Loans.Read
  python -m client.show_token bob Loans.Waiver --raw     # prints only the token, for curl
"""
import json
import sys

import jwt

from .config import get_config
from .entra_auth import UserSession

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--raw"]
    raw = "--raw" in sys.argv
    if len(args) < 2:
        sys.exit("usage: python -m client.show_token <alice|bob|dave> <Scope> [<Scope>...] [--raw]")
    cfg = get_config()
    token = UserSession(args[0], cfg.users[args[0]]).token(args[1:])
    if raw:
        print(token)
        sys.exit(0)
    c = jwt.decode(token, options={"verify_signature": False})
    for k in ("iss", "aud", "azp", "ver", "scp", "roles", "oid", "preferred_username", "exp"):
        print(f"{k:18} {c.get(k)}")
    print("\nExpected: scp == only the scope(s) you asked for; roles == the user's app roles;"
          "\n          aud == GATEWAY_CLIENT_ID (or api://...); azp == AGENT_CLIENT_ID; ver == 2.0")
