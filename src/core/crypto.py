"""Symmetric encryption for at-rest secrets (currently TOTP seeds).

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` library.
The key is derived from `settings.totp_encryption_key`. If the configured
value is already a valid Fernet key (32 urlsafe-base64 bytes decoding to
32 raw bytes) it is used verbatim; otherwise the string is hashed with
SHA-256 and urlsafe-base64 encoded to produce a valid key. This
tolerates pass-through of shorter or ad-hoc keys during dev while still
letting ops pin a proper key in prod.

Rotating the key invalidates every value previously encrypted with it —
2FA enrollments must be reset after a rotation.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from src.core.config import Settings, get_settings


def derive_fernet_key(raw_key: str) -> bytes:
    """Return a Fernet-compatible 32-byte urlsafe-base64 key.

    If `raw_key` already decodes to exactly 32 bytes of urlsafe-base64
    it is returned as-is (encoded). Otherwise it is hashed with SHA-256
    and the digest is urlsafe-base64-encoded.

    Exposed as a module-level function so tests can exercise both the
    passthrough and coerce branches without instantiating Fernet.
    """
    try:
        decoded = base64.urlsafe_b64decode(raw_key.encode("utf-8"))
    except (ValueError, base64.binascii.Error):  # type: ignore[attr-defined]
        decoded = b""

    if len(decoded) == 32:
        return raw_key.encode("utf-8")

    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet(settings: Settings | None = None) -> Fernet:
    s = settings or get_settings()
    return Fernet(derive_fernet_key(s.totp_encryption_key))


def encrypt_secret(plain: str, settings: Settings | None = None) -> str:
    """Encrypt a plaintext secret, return a urlsafe-base64 ciphertext string."""
    token = _get_fernet(settings).encrypt(plain.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(cipher: str, settings: Settings | None = None) -> str:
    """Decrypt a ciphertext string produced by `encrypt_secret`.

    Raises `cryptography.fernet.InvalidToken` on tampered or wrong-key
    ciphertext — callers should treat that as an auth failure.
    """
    plaintext = _get_fernet(settings).decrypt(cipher.encode("utf-8"))
    return plaintext.decode("utf-8")


__all__ = ["derive_fernet_key", "encrypt_secret", "decrypt_secret", "InvalidToken"]
