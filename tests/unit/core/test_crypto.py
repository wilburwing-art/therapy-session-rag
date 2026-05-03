"""Tests for the Fernet-based secret encryption helpers."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet, InvalidToken

from src.core.crypto import decrypt_secret, derive_fernet_key, encrypt_secret


@pytest.fixture
def test_settings() -> MagicMock:
    """Settings stub with a stable raw key that isn't Fernet-compatible."""
    s = MagicMock()
    s.totp_encryption_key = "some-ad-hoc-dev-key-value"
    return s


@pytest.fixture
def fernet_key_settings() -> MagicMock:
    """Settings stub holding a valid pre-generated Fernet key."""
    s = MagicMock()
    s.totp_encryption_key = Fernet.generate_key().decode("utf-8")
    return s


class TestDeriveFernetKey:
    def test_passthrough_for_valid_fernet_key(self) -> None:
        """A real Fernet key is returned byte-for-byte."""
        key = Fernet.generate_key()
        derived = derive_fernet_key(key.decode("utf-8"))
        assert derived == key

    def test_coerces_short_strings_via_sha256(self) -> None:
        """Short or arbitrary strings are hashed to 32 bytes then base64."""
        derived = derive_fernet_key("short")
        # Must be a valid Fernet key — try constructing it.
        Fernet(derived)
        # Length of a urlsafe-base64 encoded 32-byte hash is 44 with padding.
        assert len(derived) == 44

    def test_coerces_empty_string(self) -> None:
        """Even an empty key input produces a usable Fernet key."""
        derived = derive_fernet_key("")
        Fernet(derived)

    def test_coerces_non_base64_garbage(self) -> None:
        """Input that fails base64 decoding is hashed instead."""
        derived = derive_fernet_key("!!!not-valid-base64-at-all!!!")
        Fernet(derived)

    def test_deterministic_for_same_input(self) -> None:
        assert derive_fernet_key("x") == derive_fernet_key("x")

    def test_rejects_wrong_length_base64(self) -> None:
        """Valid base64 that decodes to the wrong byte count is coerced."""
        # 16 bytes base64 encodes cleanly but isn't a Fernet key.
        too_short = base64.urlsafe_b64encode(b"x" * 16).decode("utf-8")
        derived = derive_fernet_key(too_short)
        Fernet(derived)
        # Not passthrough, since 16 != 32.
        assert derived != too_short.encode("utf-8")


class TestEncryptDecryptRoundtrip:
    def test_roundtrip_arbitrary_string(self, test_settings: MagicMock) -> None:
        plain = "JBSWY3DPEHPK3PXP"  # Base32 TOTP secret shape
        cipher = encrypt_secret(plain, settings=test_settings)
        assert cipher != plain
        assert decrypt_secret(cipher, settings=test_settings) == plain

    def test_roundtrip_with_real_fernet_key(self, fernet_key_settings: MagicMock) -> None:
        plain = "secret-value-abcdef"
        cipher = encrypt_secret(plain, settings=fernet_key_settings)
        assert decrypt_secret(cipher, settings=fernet_key_settings) == plain

    def test_ciphertexts_differ_across_calls(self, test_settings: MagicMock) -> None:
        """Fernet includes an IV, so two encryptions of the same plaintext differ."""
        plain = "repeat-me"
        c1 = encrypt_secret(plain, settings=test_settings)
        c2 = encrypt_secret(plain, settings=test_settings)
        assert c1 != c2

    def test_decrypt_rejects_wrong_key(self) -> None:
        s1 = MagicMock()
        s1.totp_encryption_key = "key-one"
        s2 = MagicMock()
        s2.totp_encryption_key = "key-two"

        cipher = encrypt_secret("data", settings=s1)
        with pytest.raises(InvalidToken):
            decrypt_secret(cipher, settings=s2)

    def test_decrypt_rejects_tampered_ciphertext(self, test_settings: MagicMock) -> None:
        cipher = encrypt_secret("data", settings=test_settings)
        # Flip a middle character. Fernet's HMAC should catch it.
        tampered = cipher[:10] + ("A" if cipher[10] != "A" else "B") + cipher[11:]
        with pytest.raises(InvalidToken):
            decrypt_secret(tampered, settings=test_settings)
