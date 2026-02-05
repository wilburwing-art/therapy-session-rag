"""Transcription stage - wraps DeepgramClient for local audio files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.services.deepgram_client import DeepgramClient, TranscriptionResult

from dev.config import TranscriptionConfig

EXTENSION_MAP = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
}


def get_content_type(path: Path) -> str:
    """Determine MIME type from file extension."""
    suffix = path.suffix.lower()
    return EXTENSION_MAP.get(suffix, "audio/mpeg")


def result_to_dict(result: TranscriptionResult) -> dict[str, Any]:
    """Serialize TranscriptionResult for JSON caching."""
    return {
        "full_text": result.full_text,
        "segments": [s.to_dict() for s in result.segments],
        "duration_seconds": result.duration_seconds,
        "language": result.language,
        "confidence": result.confidence,
        "word_count": result.word_count,
    }


async def transcribe_file(
    client: DeepgramClient,
    audio_path: Path,
    config: TranscriptionConfig,
) -> dict[str, Any]:
    """Transcribe a local audio file.

    Reads audio bytes from disk and sends directly to Deepgram,
    bypassing MinIO storage entirely.
    """
    audio_data = audio_path.read_bytes()
    content_type = get_content_type(audio_path)

    result = await client.transcribe_file(
        audio_data=audio_data,
        content_type=content_type,
        language=config.language,
        enable_diarization=config.enable_diarization,
    )

    return result_to_dict(result)
