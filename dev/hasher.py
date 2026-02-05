"""Content hashing for cache key generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def file_content_hash(path: Path) -> str:
    """SHA-256 hash of file content, truncated to 16 hex chars.

    Renaming or moving a file doesn't invalidate the hash.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def config_hash(params: dict[str, Any]) -> str:
    """Deterministic hash of config parameters.

    Used to detect when tunable parameters change,
    invalidating downstream cache entries.
    """
    canonical = json.dumps(params, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:8]
