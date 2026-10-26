"""Key-management helpers."""

import secrets
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _write_rsa_pair(private_path: Path, public_path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_path.write_bytes(private_bytes)
    public_path.write_bytes(public_bytes)


def generate_test_keys(out_dir: Path) -> None:
    """Generate test key material if absent."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pairs = [
        ("idp.private.pem", "idp.public.pem"),
        ("orchestrator.private.pem", "orchestrator.public.pem"),
        ("approval.private.pem", "approval.public.pem"),
        ("attacker.private.pem", "attacker.public.pem"),
    ]
    for private_name, public_name in pairs:
        private_path = out_dir / private_name
        public_path = out_dir / public_name
        if not private_path.exists() or not public_path.exists():
            _write_rsa_pair(private_path, public_path)

    secret_path = out_dir / "backend_service_secret.txt"
    if not secret_path.exists():
        secret_path.write_text(secrets.token_hex(32), encoding="utf-8")

    readme = out_dir / "README.txt"
    if not readme.exists():
        readme.write_text("TEST KEYS ONLY\n", encoding="utf-8")
