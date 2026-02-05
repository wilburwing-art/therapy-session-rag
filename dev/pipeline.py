"""Pipeline orchestrator for the dev ingestion tool."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.models.db.consent import Consent
from src.models.db.user import User
from src.services.deepgram_client import DeepgramClient
from src.services.embedding_client import EmbeddingClient

from dev.cache import CacheManager
from dev.config import DevConfig
from dev.hasher import config_hash, file_content_hash
from dev.stages import chunk as chunk_stage
from dev.stages import embed as embed_stage
from dev.stages import load as load_stage
from dev.stages import transcribe as transcribe_stage

logger = logging.getLogger(__name__)

STAGES = ("transcribe", "chunk", "embed", "load")


@dataclass
class FileResult:
    """Result of processing a single audio file."""

    path: Path
    content_hash: str
    session_id: str | None = None
    transcript_cached: bool = False
    chunks_cached: bool = False
    embeddings_cached: bool = False
    chunk_count: int = 0
    error: str | None = None


class Pipeline:
    """Orchestrates the dev ingestion pipeline.

    Processes audio files through: transcribe -> chunk -> embed -> load,
    checking the cache at each stage to avoid redundant API calls.
    """

    def __init__(
        self,
        config: DevConfig,
        cache: CacheManager,
        db_session: AsyncSession,
        patient: User,
        therapist: User,
        consent: Consent,
        settings: Settings | None = None,
    ) -> None:
        self.config = config
        self.cache = cache
        self.db_session = db_session
        self.patient = patient
        self.therapist = therapist
        self.consent = consent

        settings = settings or get_settings()
        self._deepgram = DeepgramClient(settings=settings)
        self._embedding_client = EmbeddingClient(
            settings=settings,
            model=config.embedding.model,
        )

    async def close(self) -> None:
        """Clean up API clients."""
        await self._deepgram.close()
        await self._embedding_client.close()

    async def process_file(
        self,
        audio_path: Path,
        from_stage: str = "transcribe",
    ) -> FileResult:
        """Process a single audio file through the pipeline.

        Args:
            audio_path: Path to the audio file
            from_stage: Stage to start from. Earlier stages use cache.
                        One of: transcribe, chunk, embed, load
        """
        content_hash = file_content_hash(audio_path)
        result = FileResult(path=audio_path, content_hash=content_hash)
        stage_index = STAGES.index(from_stage)

        try:
            # --- Stage 1: Transcribe ---
            transcript_data = self._get_or_run_transcript(
                audio_path, content_hash, result, run=stage_index <= 0
            )
            if transcript_data is None:
                transcript_data = await self._run_transcription(
                    audio_path, content_hash, result
                )

            # --- Stage 2: Chunk ---
            chunk_cfg_hash = config_hash(self.config.chunking.params_dict)
            chunk_key = f"{content_hash}_{chunk_cfg_hash}"

            chunks = self._get_or_run_chunks(
                transcript_data, chunk_key, result, run=stage_index <= 1
            )
            if chunks is None:
                chunks = self._run_chunking(transcript_data, chunk_key, result)

            # --- Stage 3: Embed ---
            embed_cfg_hash = config_hash(self.config.embedding.params_dict)
            embed_key = f"{chunk_key}_{embed_cfg_hash}"

            embeddings = await self._get_or_run_embeddings(
                chunks, embed_key, result, run=stage_index <= 2
            )
            if embeddings is None:
                embeddings = await self._run_embedding(chunks, embed_key, result)

            # --- Stage 4: Load to DB ---
            session_id = await load_stage.load_to_database(
                db=self.db_session,
                audio_path=str(audio_path),
                content_hash=content_hash,
                transcript_data=transcript_data,
                chunks=chunks,
                embeddings=embeddings,
                patient=self.patient,
                therapist=self.therapist,
                consent=self.consent,
            )
            result.session_id = str(session_id)
            result.chunk_count = len(chunks)

        except Exception as e:
            result.error = str(e)
            logger.error(f"Failed to process {audio_path.name}: {e}")

        return result

    def _get_or_run_transcript(
        self,
        audio_path: Path,
        content_hash: str,
        result: FileResult,
        run: bool,
    ) -> dict[str, Any] | None:
        """Try cache for transcript. Returns None if cache miss and run=True."""
        cached = self.cache.get_transcript(content_hash)
        if cached is not None:
            result.transcript_cached = True
            logger.info(f"  [cache hit] transcript for {audio_path.name}")
            return cached
        if not run:
            raise ValueError(
                f"No cached transcript for {audio_path.name} "
                f"(hash={content_hash}). Run from 'transcribe' stage first."
            )
        return None

    async def _run_transcription(
        self,
        audio_path: Path,
        content_hash: str,
        result: FileResult,
    ) -> dict[str, Any]:
        logger.info(f"  [transcribing] {audio_path.name} ({audio_path.stat().st_size / 1e6:.1f} MB)")
        transcript_data = await transcribe_stage.transcribe_file(
            client=self._deepgram,
            audio_path=audio_path,
            config=self.config.transcription,
        )
        self.cache.save_transcript(content_hash, transcript_data)
        logger.info(
            f"  [done] {transcript_data.get('word_count', 0)} words, "
            f"{transcript_data.get('duration_seconds', 0):.0f}s"
        )
        return transcript_data

    def _get_or_run_chunks(
        self,
        transcript_data: dict[str, Any],
        chunk_key: str,
        result: FileResult,
        run: bool,
    ) -> list[dict[str, Any]] | None:
        cached = self.cache.get_chunks(chunk_key)
        if cached is not None:
            result.chunks_cached = True
            logger.info(f"  [cache hit] {len(cached)} chunks")
            return cached
        if not run:
            return None  # Will fall through to _run_chunking
        return None

    def _run_chunking(
        self,
        transcript_data: dict[str, Any],
        chunk_key: str,
        result: FileResult,
    ) -> list[dict[str, Any]]:
        logger.info("  [chunking] splitting transcript")
        chunks = chunk_stage.chunk_transcript(transcript_data, self.config.chunking)
        self.cache.save_chunks(chunk_key, chunks)
        logger.info(f"  [done] {len(chunks)} chunks")
        return chunks

    async def _get_or_run_embeddings(
        self,
        chunks: list[dict[str, Any]],
        embed_key: str,
        result: FileResult,
        run: bool,
    ) -> list[dict[str, Any]] | None:
        cached = self.cache.get_embeddings(embed_key)
        if cached is not None:
            result.embeddings_cached = True
            logger.info(f"  [cache hit] {len(cached)} embeddings")
            return cached
        if not run:
            return None
        return None

    async def _run_embedding(
        self,
        chunks: list[dict[str, Any]],
        embed_key: str,
        result: FileResult,
    ) -> list[dict[str, Any]]:
        logger.info(f"  [embedding] {len(chunks)} chunks")
        embeddings = await embed_stage.embed_chunks(self._embedding_client, chunks)
        self.cache.save_embeddings(embed_key, embeddings)
        logger.info(f"  [done] {len(embeddings)} embeddings")
        return embeddings

    def discover_audio_files(self, source_dir: Path) -> list[Path]:
        """Find all audio files in a directory."""
        files: list[Path] = []
        for ext in self.config.audio.extensions:
            files.extend(source_dir.glob(f"*.{ext}"))
            files.extend(source_dir.glob(f"**/*.{ext}"))

        # Deduplicate (glob patterns can overlap) and sort
        unique = sorted(set(files))
        return unique
