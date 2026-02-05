"""Tests for security utilities."""

from src.core.security import (
    API_KEY_LENGTH,
    API_KEY_PREFIX,
    create_api_key,
    generate_api_key,
    hash_api_key,
    is_valid_api_key_format,
    verify_api_key,
)


class TestGenerateApiKey:
    """Tests for generate_api_key function."""

    def test_generates_key_with_prefix(self) -> None:
        """Test that generated key has correct prefix."""
        key = generate_api_key()
        assert key.startswith(API_KEY_PREFIX)

    def test_generates_unique_keys(self) -> None:
        """Test that each call generates a unique key."""
        keys = {generate_api_key() for _ in range(100)}
        assert len(keys) == 100

    def test_generates_correct_length(self) -> None:
        """Test that generated key has correct length."""
        key = generate_api_key()
        expected_length = len(API_KEY_PREFIX) + (API_KEY_LENGTH * 2)
        assert len(key) == expected_length


class TestHashAndVerify:
    """Tests for hash_api_key and verify_api_key functions."""

    def test_hash_creates_different_output(self) -> None:
        """Test that hashing creates different output than input."""
        key = generate_api_key()
        hashed = hash_api_key(key)
        assert hashed != key

    def test_verify_correct_key(self) -> None:
        """Test that verification succeeds with correct key."""
        key = generate_api_key()
        hashed = hash_api_key(key)
        assert verify_api_key(key, hashed) is True

    def test_verify_wrong_key(self) -> None:
        """Test that verification fails with wrong key."""
        key1 = generate_api_key()
        key2 = generate_api_key()
        hashed = hash_api_key(key1)
        assert verify_api_key(key2, hashed) is False

    def test_same_key_same_hash(self) -> None:
        """Test that same key produces same hash (deterministic HMAC)."""
        key = generate_api_key()
        hash1 = hash_api_key(key)
        hash2 = hash_api_key(key)
        # HMAC is deterministic - same input = same output
        assert hash1 == hash2
        assert verify_api_key(key, hash1) is True


class TestCreateApiKey:
    """Tests for create_api_key function."""

    def test_returns_key_and_hash(self) -> None:
        """Test that create_api_key returns both key and hash."""
        key, hashed = create_api_key()
        assert key.startswith(API_KEY_PREFIX)
        assert hashed != key
        assert verify_api_key(key, hashed) is True


class TestIsValidApiKeyFormat:
    """Tests for is_valid_api_key_format function."""

    def test_valid_format(self) -> None:
        """Test that valid key format is recognized."""
        key = generate_api_key()
        assert is_valid_api_key_format(key) is True

    def test_invalid_prefix(self) -> None:
        """Test that invalid prefix is rejected."""
        assert is_valid_api_key_format("invalid_prefix_key") is False

    def test_wrong_length(self) -> None:
        """Test that wrong length is rejected."""
        assert is_valid_api_key_format(f"{API_KEY_PREFIX}tooshort") is False
        assert is_valid_api_key_format(f"{API_KEY_PREFIX}{'a' * 100}") is False

    def test_empty_string(self) -> None:
        """Test that empty string is rejected."""
        assert is_valid_api_key_format("") is False
