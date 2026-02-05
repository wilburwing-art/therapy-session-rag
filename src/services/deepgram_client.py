"""Deepgram client for audio transcription."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class DeepgramError(Exception):
    """Error from Deepgram API."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Word:
    """A single word with timing information."""

    word: str
    start: float
    end: float
    confidence: float
    speaker: int | None = None


@dataclass
class Segment:
    """A transcript segment with speaker information."""

    text: str
    start_time: float
    end_time: float
    speaker: str | None = None
    confidence: float | None = None
    words: list[Word] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "text": self.text,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "speaker": self.speaker,
            "confidence": self.confidence,
            "words": [
                {
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "confidence": w.confidence,
                    "speaker": w.speaker,
                }
                for w in self.words
            ],
        }


@dataclass
class TranscriptionResult:
    """Result from Deepgram transcription."""

    full_text: str
    segments: list[Segment]
    duration_seconds: float
    language: str | None = None
    confidence: float | None = None
    word_count: int = 0


class DeepgramClient:
    """Client for Deepgram transcription API.

    Provides methods for transcribing audio files with speaker
    diarization support.
    """

    BASE_URL = "https://api.deepgram.com/v1"
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize Deepgram client.

        Args:
            settings: Application settings. If None, loads from environment.
        """
        self.settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client (lazy initialization)."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"Token {self.settings.deepgram_api_key}",
                    "Content-Type": "audio/*",
                },
                timeout=300.0,  # 5 minute timeout for long audio files
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def transcribe_file(
        self,
        audio_data: bytes,
        content_type: str = "audio/mpeg",
        language: str = "en",
        enable_diarization: bool = True,
        punctuate: bool = True,
        utterances: bool = True,
    ) -> TranscriptionResult:
        """Transcribe an audio file.

        Args:
            audio_data: Raw audio file bytes
            content_type: MIME type of the audio
            language: Language code (e.g., "en", "es")
            enable_diarization: Enable speaker diarization
            punctuate: Add punctuation to transcript
            utterances: Group words into utterances

        Returns:
            TranscriptionResult with full text and segments

        Raises:
            DeepgramError: If transcription fails
        """
        params = {
            "model": "nova-2",
            "language": language,
            "punctuate": str(punctuate).lower(),
            "utterances": str(utterances).lower(),
            "smart_format": "true",
        }

        if enable_diarization:
            params["diarize"] = "true"

        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self.client.post(
                    "/listen",
                    params=params,
                    content=audio_data,
                    headers={"Content-Type": content_type},
                )

                if response.status_code == 429:
                    # Rate limited, wait and retry
                    retry_after = int(response.headers.get("Retry-After", "5"))
                    logger.warning(
                        f"Rate limited, retrying after {retry_after}s "
                        f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                    )
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code >= 500:
                    # Server error, retry with exponential backoff
                    delay = self.RETRY_DELAY * (2**attempt)
                    logger.warning(
                        f"Server error {response.status_code}, "
                        f"retrying in {delay}s (attempt {attempt + 1}/{self.MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                    continue

                if response.status_code != 200:
                    error_body = response.text
                    raise DeepgramError(
                        f"Transcription failed: {error_body}",
                        status_code=response.status_code,
                    )

                return self._parse_response(response.json())

            except httpx.TimeoutException as e:
                last_error = e
                delay = self.RETRY_DELAY * (2**attempt)
                logger.warning(
                    f"Request timeout, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                )
                await asyncio.sleep(delay)
                continue

            except httpx.RequestError as e:
                last_error = e
                delay = self.RETRY_DELAY * (2**attempt)
                logger.warning(
                    f"Request error: {e}, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                )
                await asyncio.sleep(delay)
                continue

        raise DeepgramError(
            f"Transcription failed after {self.MAX_RETRIES} attempts: {last_error}"
        )

    def _parse_response(self, data: dict[str, Any]) -> TranscriptionResult:
        """Parse Deepgram API response.

        Args:
            data: JSON response from Deepgram

        Returns:
            Parsed TranscriptionResult
        """
        results = data.get("results", {})
        channels = results.get("channels", [])

        if not channels:
            return TranscriptionResult(
                full_text="",
                segments=[],
                duration_seconds=0.0,
            )

        channel = channels[0]
        alternatives = channel.get("alternatives", [])

        if not alternatives:
            return TranscriptionResult(
                full_text="",
                segments=[],
                duration_seconds=0.0,
            )

        alternative = alternatives[0]
        full_text = alternative.get("transcript", "")
        confidence = alternative.get("confidence")

        # Parse words for detailed information
        raw_words = alternative.get("words", [])
        words = [
            Word(
                word=w.get("word", ""),
                start=w.get("start", 0.0),
                end=w.get("end", 0.0),
                confidence=w.get("confidence", 0.0),
                speaker=w.get("speaker"),
            )
            for w in raw_words
        ]

        # Get duration from metadata
        metadata = data.get("metadata", {})
        duration = metadata.get("duration", 0.0)
        detected_language = results.get("detected_language", metadata.get("language"))

        # Parse utterances if available, otherwise create segments from words
        utterances = results.get("utterances", [])
        segments: list[Segment] = []

        if utterances:
            for u in utterances:
                segment_words = [
                    Word(
                        word=w.get("word", ""),
                        start=w.get("start", 0.0),
                        end=w.get("end", 0.0),
                        confidence=w.get("confidence", 0.0),
                        speaker=w.get("speaker"),
                    )
                    for w in u.get("words", [])
                ]

                speaker = u.get("speaker")
                speaker_label = f"Speaker {speaker}" if speaker is not None else None

                segments.append(
                    Segment(
                        text=u.get("transcript", ""),
                        start_time=u.get("start", 0.0),
                        end_time=u.get("end", 0.0),
                        speaker=speaker_label,
                        confidence=u.get("confidence"),
                        words=segment_words,
                    )
                )
        elif words:
            # Group words by speaker if diarization is enabled
            current_speaker: int | None = None
            current_segment_words: list[Word] = []
            current_text: list[str] = []
            segment_start: float = 0.0

            for word in words:
                if word.speaker != current_speaker and current_text:
                    # Save current segment
                    speaker_label = (
                        f"Speaker {current_speaker}"
                        if current_speaker is not None
                        else None
                    )
                    segments.append(
                        Segment(
                            text=" ".join(current_text),
                            start_time=segment_start,
                            end_time=current_segment_words[-1].end,
                            speaker=speaker_label,
                            words=current_segment_words,
                        )
                    )
                    current_text = []
                    current_segment_words = []
                    segment_start = word.start

                if not current_text:
                    segment_start = word.start

                current_speaker = word.speaker
                current_text.append(word.word)
                current_segment_words.append(word)

            # Save final segment
            if current_text:
                speaker_label = (
                    f"Speaker {current_speaker}"
                    if current_speaker is not None
                    else None
                )
                segments.append(
                    Segment(
                        text=" ".join(current_text),
                        start_time=segment_start,
                        end_time=current_segment_words[-1].end,
                        speaker=speaker_label,
                        words=current_segment_words,
                    )
                )

        return TranscriptionResult(
            full_text=full_text,
            segments=segments,
            duration_seconds=duration,
            language=detected_language,
            confidence=confidence,
            word_count=len(words),
        )
