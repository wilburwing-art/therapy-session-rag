"""Service for generating LLM-based recaps of therapy sessions.

Loads the session's transcript, prompts Claude for a structured JSON
recap (brief, topics, tone, homework, follow-ups, risk flags), parses
the response, and persists it. Designed to be called from either the
summarization worker (automatic, after embedding) or an API endpoint
(manual regeneration).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.exceptions import NotFoundError
from src.models.domain.session_recap import (
    HomeworkItem,
    SessionRecapPayload,
    SessionRecapRead,
)
from src.repositories.homework_repo import HomeworkRepository
from src.repositories.session_recap_repo import SessionRecapRepository
from src.repositories.session_repo import SessionRepository
from src.repositories.transcript_repo import TranscriptRepository
from src.services.claude_client import ClaudeClient, ClaudeError, Message

logger = logging.getLogger(__name__)

# Telemetry is opt-in — guard the import so a missing/broken OTEL install
# never breaks summarization. Falls back to a no-op context manager.
try:
    from src.core.telemetry import record_duration as _record_duration
except ImportError:  # pragma: no cover - defensive

    @contextmanager
    def _record_duration(
        operation: str,  # noqa: ARG001 - signature-compat no-op stub
        attributes: dict[str, str] | None = None,  # noqa: ARG001
    ) -> Iterator[None]:
        yield


_MAX_TRANSCRIPT_CHARS = 120_000


class SummarizationServiceError(Exception):
    """Error generating a session recap."""


SYSTEM_PROMPT = """You are a clinical documentation assistant generating a recap of a single therapy session for the therapist's own review.

Your output MUST be a single JSON object matching exactly this schema — no prose before or after, no markdown fences:

{
  "brief": "2-3 sentence overview of what the session covered. Factual, descriptive.",
  "key_topics": ["topic 1", "topic 2", ...],
  "emotional_tone": "short phrase describing overall tone, e.g. 'anxious, reflective'. null if unclear.",
  "homework_assigned": [
    {"task": "what patient will do between sessions", "notes": "optional context or null"}
  ],
  "follow_ups": ["topic to revisit next session", ...],
  "risk_flags": ["any concerning statements, using quotes or paraphrase + approximate timestamp"]
}

RULES:
1. Only describe what was actually discussed. Do not infer diagnoses, add clinical judgment, or speculate about the patient's inner state beyond what they said.
2. Do not prescribe treatment or invent interventions the therapist didn't propose.
3. For risk_flags, only flag explicit statements of suicidal ideation, self-harm, harm to others, abuse disclosures, or disclosures that may trigger mandatory reporting. Use the patient's own language where possible.
4. If the transcript is too short or non-clinical to summarize meaningfully, return a minimal brief and empty arrays.
5. Keep key_topics, follow_ups, and risk_flags to at most 10 items each. Keep homework_assigned to at most 10 items.
6. Return ONLY the JSON object. No explanation, no apologies, no preamble."""


class SummarizationService:
    """Generates and persists structured recaps of therapy sessions."""

    def __init__(
        self,
        db_session: AsyncSession,
        settings: Settings | None = None,
        claude_client: ClaudeClient | None = None,
    ) -> None:
        self.db_session = db_session
        self.settings = settings or get_settings()
        self.session_repo = SessionRepository(db_session)
        self.transcript_repo = TranscriptRepository(db_session)
        self.recap_repo = SessionRecapRepository(db_session)
        self.homework_repo = HomeworkRepository(db_session)
        self._claude_client: ClaudeClient | None = claude_client

    @property
    def claude_client(self) -> ClaudeClient:
        if self._claude_client is None:
            self._claude_client = ClaudeClient(settings=self.settings)
        return self._claude_client

    async def generate_recap(
        self,
        session_id: uuid.UUID,
        intake_context: str | None = None,
    ) -> SessionRecapRead:
        """Generate a recap for a session and persist it.

        If ``intake_context`` is provided, it is prepended to the LLM
        prompt as the patient's self-reported background so the recap
        can reference it (e.g. "patient's intake flagged sleep issues").
        The parameter is optional to preserve existing call sites.

        Raises:
            NotFoundError: if the session or its transcript is missing.
            SummarizationServiceError: if the LLM call or parsing fails.
        """
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundError(resource="Session", resource_id=str(session_id))

        transcript = await self.transcript_repo.get_transcript_by_session_id(session_id)
        if not transcript:
            raise NotFoundError(
                resource="Transcript",
                detail=f"No transcript found for session {session_id}",
            )

        transcript_body = self._format_transcript_for_prompt(
            full_text=transcript.full_text,
            segments=transcript.segments,
        )

        intake_block = (
            f"PATIENT INTAKE (self-reported, pre-session):\n{intake_context.strip()}\n\n"
            if intake_context and intake_context.strip()
            else ""
        )
        user_message = (
            "Here is the full transcript of a therapy session. "
            "Produce the JSON recap per the system instructions.\n\n"
            f"{intake_block}"
            "TRANSCRIPT:\n"
            f"{transcript_body}"
        )

        try:
            with _record_duration("summarization.recap"):
                response = await self.claude_client.chat(
                    messages=[Message(role="user", content=user_message)],
                    system_prompt=SYSTEM_PROMPT,
                    max_tokens=2048,
                    temperature=0.2,
                )
        except ClaudeError as exc:
            logger.error("Claude error generating recap for %s: %s", session_id, exc)
            raise SummarizationServiceError(f"LLM call failed: {exc}") from exc

        payload = self._parse_payload(response.content)

        recap = await self.recap_repo.upsert(
            session_id=session_id,
            brief=payload.brief,
            key_topics=payload.key_topics,
            emotional_tone=payload.emotional_tone,
            homework_assigned=[item.model_dump() for item in payload.homework_assigned],
            follow_ups=payload.follow_ups,
            risk_flags=payload.risk_flags,
            model_name=response.model,
        )

        logger.info(
            "Generated recap for session %s (model=%s, risk_flags=%d)",
            session_id,
            response.model,
            len(payload.risk_flags),
        )

        # Materialize homework rows so patients can track them in the
        # web app. Idempotent on (session_id, task_hash): re-running
        # recap generation will not duplicate or reset rows patients
        # may have already ticked off.
        if payload.homework_assigned:
            try:
                created = await self.homework_repo.upsert_many_for_session(
                    session_id=session_id,
                    patient_id=session.patient_id,
                    organization_id=session.patient.organization_id,
                    items=[item.model_dump() for item in payload.homework_assigned],
                )
                logger.info(
                    "Materialized %d homework row(s) for session %s",
                    created,
                    session_id,
                )
            except Exception as exc:  # pragma: no cover - defensive
                # Homework materialization must not fail recap generation;
                # recap is the source of truth and can be re-run later.
                logger.warning(
                    "Failed to materialize homework for session %s: %s",
                    session_id,
                    exc,
                )

        return self._to_read(recap)

    async def get_recap(self, session_id: uuid.UUID) -> SessionRecapRead:
        """Get an existing recap. Raises NotFoundError if none exists yet."""
        recap = await self.recap_repo.get_by_session_id(session_id)
        if not recap:
            raise NotFoundError(
                resource="SessionRecap",
                detail=f"No recap exists for session {session_id}",
            )
        return self._to_read(recap)

    async def delete_recap(self, session_id: uuid.UUID) -> bool:
        deleted = await self.recap_repo.delete_by_session_id(session_id)
        return deleted > 0

    @staticmethod
    def _format_transcript_for_prompt(
        full_text: str,
        segments: list[dict[str, Any]],
    ) -> str:
        """Render the transcript for the LLM prompt.

        Prefers segments with speaker + timestamps when available so the
        model can attribute quotes; falls back to the raw full_text.
        Truncates to keep context manageable.
        """
        if segments:
            lines: list[str] = []
            for seg in segments:
                text = (seg.get("text") or "").strip()
                if not text:
                    continue
                speaker = seg.get("speaker") or "Speaker"
                start = seg.get("start_time")
                if start is None:
                    start = seg.get("start")
                if isinstance(start, (int, float)):
                    lines.append(f"[{start:.1f}s] {speaker}: {text}")
                else:
                    lines.append(f"{speaker}: {text}")
            rendered = "\n".join(lines)
        else:
            rendered = full_text

        if len(rendered) > _MAX_TRANSCRIPT_CHARS:
            rendered = (
                rendered[: _MAX_TRANSCRIPT_CHARS // 2]
                + "\n\n[...transcript truncated for length...]\n\n"
                + rendered[-_MAX_TRANSCRIPT_CHARS // 2 :]
            )
        return rendered

    @staticmethod
    def _parse_payload(raw: str) -> SessionRecapPayload:
        """Parse Claude's JSON output into SessionRecapPayload.

        Tolerates minor output quirks: markdown code fences, trailing
        explanation. Raises SummarizationServiceError on unrecoverable
        malformed output.
        """
        candidate = raw.strip()

        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
        if fence_match:
            candidate = fence_match.group(1)
        else:
            brace_start = candidate.find("{")
            brace_end = candidate.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                candidate = candidate[brace_start : brace_end + 1]

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            logger.error("Failed to decode recap JSON: %s\nRaw: %s", exc, raw[:500])
            raise SummarizationServiceError("LLM returned non-JSON output") from exc

        SummarizationService._normalize_homework(data)

        try:
            return SessionRecapPayload.model_validate(data)
        except PydanticValidationError as exc:
            logger.error("Recap payload failed validation: %s", exc)
            raise SummarizationServiceError(
                f"LLM output did not match expected schema: {exc}"
            ) from exc

    @staticmethod
    def _normalize_homework(data: dict[str, Any]) -> None:
        """Accept homework entries that come back as bare strings."""
        homework = data.get("homework_assigned")
        if not isinstance(homework, list):
            return
        normalized: list[dict[str, str | None]] = []
        for entry in homework:
            if isinstance(entry, str):
                normalized.append({"task": entry, "notes": None})
            elif isinstance(entry, dict):
                task = entry.get("task")
                if isinstance(task, str) and task.strip():
                    notes = entry.get("notes")
                    normalized.append(
                        {
                            "task": task,
                            "notes": notes if isinstance(notes, str) else None,
                        }
                    )
        data["homework_assigned"] = normalized

    @staticmethod
    def _to_read(recap: Any) -> SessionRecapRead:
        return SessionRecapRead(
            id=recap.id,
            session_id=recap.session_id,
            brief=recap.brief,
            key_topics=list(recap.key_topics or []),
            emotional_tone=recap.emotional_tone,
            homework_assigned=[HomeworkItem(**item) for item in (recap.homework_assigned or [])],
            follow_ups=list(recap.follow_ups or []),
            risk_flags=list(recap.risk_flags or []),
            model_name=recap.model_name,
            generated_at=recap.generated_at,
            created_at=recap.created_at,
            updated_at=recap.updated_at,
        )
