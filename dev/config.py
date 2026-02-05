"""Dev pipeline configuration loader."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(__file__).parent
DEFAULT_CONFIG = CONFIG_DIR / "dev_config.toml"
LOCAL_CONFIG = CONFIG_DIR / "dev_config.local.toml"


@dataclass
class AudioConfig:
    source_dir: str = ""
    extensions: list[str] = field(
        default_factory=lambda: ["mp3", "wav", "webm", "ogg", "flac", "m4a"]
    )


@dataclass
class TranscriptionConfig:
    language: str = "en"
    enable_diarization: bool = True


@dataclass
class ChunkingConfig:
    target_chunk_size: int = 500
    max_chunk_size: int = 750
    min_chunk_size: int = 100

    @property
    def params_dict(self) -> dict[str, int]:
        """Parameters that affect chunk output (for cache key hashing)."""
        return {
            "target_chunk_size": self.target_chunk_size,
            "max_chunk_size": self.max_chunk_size,
            "min_chunk_size": self.min_chunk_size,
        }


@dataclass
class EmbeddingConfig:
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    batch_size: int = 100

    @property
    def params_dict(self) -> dict[str, str | int]:
        """Parameters that affect embedding output (for cache key hashing)."""
        return {
            "model": self.model,
            "dimensions": self.dimensions,
        }


@dataclass
class ChatConfig:
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.7
    top_k: int = 5


@dataclass
class DevConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    chat: ChatConfig = field(default_factory=ChatConfig)
    cache_dir: str = "dev_data/cache"
    max_concurrent: int = 2


def _merge_dicts(base: dict, override: dict) -> dict:
    """Deep merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Path | None = None) -> DevConfig:
    """Load dev config from TOML files.

    Loads default config, then merges local overrides on top,
    then merges explicit config_path on top of that.
    """
    # Load default
    with open(DEFAULT_CONFIG, "rb") as f:
        data = tomllib.load(f)

    # Merge local overrides if they exist
    if LOCAL_CONFIG.exists():
        with open(LOCAL_CONFIG, "rb") as f:
            local_data = tomllib.load(f)
        data = _merge_dicts(data, local_data)

    # Merge explicit config if provided
    if config_path and config_path.exists():
        with open(config_path, "rb") as f:
            explicit_data = tomllib.load(f)
        data = _merge_dicts(data, explicit_data)

    # Build config dataclasses
    dev_section = data.get("dev", {})
    return DevConfig(
        audio=AudioConfig(**data.get("audio", {})),
        transcription=TranscriptionConfig(**data.get("transcription", {})),
        chunking=ChunkingConfig(**data.get("chunking", {})),
        embedding=EmbeddingConfig(**data.get("embedding", {})),
        chat=ChatConfig(**data.get("chat", {})),
        cache_dir=dev_section.get("cache_dir", "dev_data/cache"),
        max_concurrent=dev_section.get("max_concurrent", 2),
    )
