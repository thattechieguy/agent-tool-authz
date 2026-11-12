"""Sign a test user in once:  python -m client.login alice"""
import sys

from .config import get_config
from .entra_auth import UserSession

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("alice", "bob", "dave"):
        sys.exit("usage: python -m client.login <alice|bob|dave>")
    cfg = get_config()
    UserSession(sys.argv[1], cfg.users[sys.argv[1]]).login()
    print(f"{sys.argv[1]} signed in; token cache saved under .token_cache/")
