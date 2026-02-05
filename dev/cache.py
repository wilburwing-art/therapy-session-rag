"""Multi-layer file cache for pipeline results."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any


class CacheManager:
    """File-based cache with separate layers for each pipeline stage.

    Cache keys incorporate content hash and config hashes so that
    parameter changes automatically invalidate downstream results.
    """

    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.transcripts_dir = self.cache_dir / "transcripts"
        self.chunks_dir = self.cache_dir / "chunks"
        self.embeddings_dir = self.cache_dir / "embeddings"

        for d in (self.transcripts_dir, self.chunks_dir, self.embeddings_dir):
            d.mkdir(parents=True, exist_ok=True)

    # --- Transcripts (keyed by content hash only) ---

    def get_transcript(self, content_hash: str) -> dict[str, Any] | None:
        path = self.transcripts_dir / f"{content_hash}.json"
        if path.exists():
            return json.loads(path.read_text())
        return None

    def save_transcript(self, content_hash: str, data: dict[str, Any]) -> None:
        self._atomic_write(self.transcripts_dir / f"{content_hash}.json", data)

    # --- Chunks (keyed by content hash + chunk config hash) ---

    def get_chunks(self, cache_key: str) -> list[dict[str, Any]] | None:
        path = self.chunks_dir / f"{cache_key}.json"
        if path.exists():
            return json.loads(path.read_text())
        return None

    def save_chunks(self, cache_key: str, data: list[dict[str, Any]]) -> None:
        self._atomic_write(self.chunks_dir / f"{cache_key}.json", data)

    # --- Embeddings (keyed by content hash + chunk config hash + embed config hash) ---

    def get_embeddings(self, cache_key: str) -> list[dict[str, Any]] | None:
        path = self.embeddings_dir / f"{cache_key}.json"
        if path.exists():
            return json.loads(path.read_text())
        return None

    def save_embeddings(self, cache_key: str, data: list[dict[str, Any]]) -> None:
        self._atomic_write(self.embeddings_dir / f"{cache_key}.json", data)

    # --- Management ---

    def clear_stage(self, stage: str) -> int:
        """Clear cache for a specific stage. Returns count of files deleted."""
        dirs = {
            "transcripts": self.transcripts_dir,
            "chunks": self.chunks_dir,
            "embeddings": self.embeddings_dir,
        }
        target = dirs.get(stage)
        if not target or not target.exists():
            return 0

        count = sum(1 for f in target.glob("*.json"))
        if count > 0:
            shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
        return count

    def clear_all(self) -> int:
        """Clear all cached data. Returns total files deleted."""
        total = 0
        for stage in ("transcripts", "chunks", "embeddings"):
            total += self.clear_stage(stage)
        return total

    def get_stats(self) -> dict[str, dict[str, int]]:
        """Return counts and total size for each cache layer."""
        stats: dict[str, dict[str, int]] = {}
        for name, directory in [
            ("transcripts", self.transcripts_dir),
            ("chunks", self.chunks_dir),
            ("embeddings", self.embeddings_dir),
        ]:
            files = list(directory.glob("*.json"))
            total_bytes = sum(f.stat().st_size for f in files)
            stats[name] = {"count": len(files), "size_bytes": total_bytes}
        return stats

    def _atomic_write(self, path: Path, data: Any) -> None:
        """Write JSON atomically (write to temp, then rename)."""
        content = json.dumps(data, indent=2)
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with open(fd, "w") as f:
                f.write(content)
            Path(tmp_path).rename(path)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise
