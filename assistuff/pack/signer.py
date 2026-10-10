"""ed25519 package signing."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class SigningError(RuntimeError):
    pass


def _require_crypto():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
        from cryptography.hazmat.primitives import serialization
    except ImportError as exc:
        raise SigningError(
            "cryptography is required for signing; install with: pip install 'assistuff[pack]'"
        ) from exc
    return Ed25519PrivateKey, Ed25519PublicKey, serialization


def generate_keypair(key_dir: Path, name: str = "default") -> tuple[Path, Path]:
    Ed25519PrivateKey, _Pub, serialization = _require_crypto()
    key_dir.mkdir(parents=True, exist_ok=True)
    priv_path = key_dir / f"{name}.key"
    pub_path = key_dir / f"{name}.pub"
    private = Ed25519PrivateKey.generate()
    priv_bytes = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    priv_path.write_bytes(priv_bytes)
    pub_path.write_bytes(pub_bytes)
    priv_path.chmod(0o600)
    logger.info("generated keypair: %s, %s", priv_path, pub_path)
    return priv_path, pub_path


def sign_payload(payload: bytes, private_key_path: Path) -> bytes:
    Ed25519PrivateKey, _Pub, serialization = _require_crypto()
    raw = private_key_path.read_bytes()
    private = Ed25519PrivateKey.from_private_bytes(raw)
    return private.sign(payload)


def verify_signature(payload: bytes, signature: bytes, public_key_path: Path) -> bool:
    _Priv, Ed25519PublicKey, serialization = _require_crypto()
    from cryptography.exceptions import InvalidSignature
    raw = public_key_path.read_bytes()
    public = Ed25519PublicKey.from_public_bytes(raw)
    try:
        public.verify(signature, payload)
        return True
    except InvalidSignature:
        return False


def sign_manifest_and_hashes(
    manifest_bytes: bytes,
    weights_hashes_bytes: bytes,
    private_key_path: Path,
) -> bytes:
    """Sign the concatenation of manifest + weights hashes."""
    payload = manifest_bytes + b"\n---\n" + weights_hashes_bytes
    return sign_payload(payload, private_key_path)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")