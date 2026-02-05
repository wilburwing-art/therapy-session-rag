"""Security utilities for API key hashing and verification."""

import hashlib
import hmac
import secrets

# API key prefix for identification
API_KEY_PREFIX = "trag_"
API_KEY_LENGTH = 32  # 32 bytes = 256 bits of entropy

# Secret for HMAC hashing (in production, this should come from environment)
# Using a fixed salt since API keys are already high-entropy
_HASH_SECRET = b"therapy-rag-api-key-hash-v1"


def generate_api_key() -> str:
    """Generate a new API key with prefix.

    Returns:
        A new API key in format: trag_<random_hex>
    """
    random_part = secrets.token_hex(API_KEY_LENGTH)
    return f"{API_KEY_PREFIX}{random_part}"


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage using HMAC-SHA256.

    Since API keys are already high-entropy random strings,
    we use HMAC-SHA256 which is fast and secure for this use case.

    Args:
        api_key: The plaintext API key to hash

    Returns:
        The hex-encoded HMAC-SHA256 hash
    """
    return hmac.new(
        _HASH_SECRET,
        api_key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Verify a plaintext API key against its hash.

    Args:
        plain_key: The plaintext API key to verify
        hashed_key: The stored hash to verify against

    Returns:
        True if the key matches, False otherwise
    """
    computed_hash = hash_api_key(plain_key)
    return hmac.compare_digest(computed_hash, hashed_key)


def create_api_key() -> tuple[str, str]:
    """Generate a new API key and its hash.

    Returns:
        A tuple of (plaintext_key, hashed_key)
        The plaintext key should be shown once to the user, then discarded.
        Only the hash should be stored.
    """
    key = generate_api_key()
    hashed = hash_api_key(key)
    return key, hashed


def is_valid_api_key_format(api_key: str) -> bool:
    """Check if an API key has valid format.

    Args:
        api_key: The API key to validate

    Returns:
        True if the format is valid, False otherwise
    """
    if not api_key.startswith(API_KEY_PREFIX):
        return False
    # Check length: prefix + 64 hex chars (32 bytes * 2)
    expected_length = len(API_KEY_PREFIX) + (API_KEY_LENGTH * 2)
    return len(api_key) == expected_length
