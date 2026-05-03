"""Service for synthesizing cross-session themes for a patient.

Pulls the patient's recent session recaps and asks Claude to produce
a structured theme document: recurring topics, emotional patterns,
coping strategies, progress indicators, and ongoing concerns. Designed
to be refreshed on demand from the therapist dashboard.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.exceptions import NotFoundError
from src.models.domain.patient_themes import (
    CopingStrategy,
    EmotionalPattern,
    PatientThemesPayload,
    PatientThemesRead,
    RecurringTopic,
)
from src.repositories.patient_themes_repo import PatientThemesRepository
from src.services.claude_client import ClaudeClient, ClaudeError, Message

logger = logging.getLogger(__name__)


class ThemesServiceError(Exception):
    """Error synthesizing patient themes."""


SYSTEM_PROMPT = """You are a clinical documentation assistant synthesizing cross-session themes from a set of single-session recaps, for the therapist's own review.

You will be given one or more session recaps in chronological order (oldest first). Produce a single JSON object, with no prose and no markdown fences, matching exactly this schema:

{
  "recurring_topics": [
    {"topic": "short name", "session_count": 3, "summary": "one-sentence characterization or null"}
  ],
  "emotional_patterns": [
    {"pattern": "short name", "evidence": "paraphrased evidence or null"}
  ],
  "coping_strategies": [
    {"strategy": "strategy name", "notes": "outcome or commitment level or null"}
  ],
  "progress_indicators": ["observed improvement or positive shift"],
  "ongoing_concerns": ["unresolved concern that recurs"]
}

RULES:
1. Only synthesize from what is in the recaps. Do not invent topics, pattern names, or strategies the recaps don't mention.
2. Do not diagnose. Do not name clinical conditions the recaps don't name.
3. "recurring_topics" should only include items that appear in 2 or more session recaps. If none qualify, return an empty list.
4. Be concise; each list at most 10 entries. Prefer fewer, higher-signal entries.
5. Output ONLY the JSON object."""


class ThemesService:
    """Generates and retrieves cross-session theme summaries per patient."""

    MIN_RECAPS_TO_SYNTHESIZE = 2

    def __init__(
        self,
        db_session: AsyncSession,
        settings: Settings | None = None,
        claude_client: ClaudeClient | None = None,
    ) -> None:
        self.db_session = db_session
        self.settings = settings or get_settings()
        self.repo = PatientThemesRepository(db_session)
        self._claude_client: ClaudeClient | None = claude_client

    @property
    def claude_client(self) -> ClaudeClient:
        if self._claude_client is None:
            self._claude_client = ClaudeClient(settings=self.settings)
        return self._claude_client

    async def generate_themes(self, patient_id: uuid.UUID) -> PatientThemesRead:
        """Synthesize themes for a patient from their recent session recaps.

        Raises:
            ThemesServiceError: if there aren't enough recaps yet or the
                LLM response can't be parsed.
        """
        recaps = await self.repo.list_recaps_for_patient(patient_id, limit=25)
        if len(recaps) < self.MIN_RECAPS_TO_SYNTHESIZE:
            raise ThemesServiceError(
                f"Need at least {self.MIN_RECAPS_TO_SYNTHESIZE} session recaps "
                f"to synthesize themes (have {len(recaps)})"
            )

        chronological = list(reversed(recaps))
        user_message = (
            "Here are session recaps in chronological order. "
            "Synthesize themes per the system instructions.\n\n"
            + self._format_recaps(chronological)
        )

        try:
            response = await self.claude_client.chat(
                messages=[Message(role="user", content=user_message)],
                system_prompt=SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.2,
            )
        except ClaudeError as exc:
            logger.error("Claude error generating themes for %s: %s", patient_id, exc)
            raise ThemesServiceError(f"LLM call failed: {exc}") from exc

        payload = self._parse_payload(response.content)

        themes = await self.repo.upsert(
            patient_id=patient_id,
            recurring_topics=[t.model_dump() for t in payload.recurring_topics],
            emotional_patterns=[p.model_dump() for p in payload.emotional_patterns],
            coping_strategies=[s.model_dump() for s in payload.coping_strategies],
            progress_indicators=payload.progress_indicators,
            ongoing_concerns=payload.ongoing_concerns,
            source_session_count=len(recaps),
            model_name=response.model,
        )

        logger.info(
            "Generated themes for patient %s from %d recaps (model=%s)",
            patient_id,
            len(recaps),
            response.model,
        )
        return self._to_read(themes)

    async def get_themes(self, patient_id: uuid.UUID) -> PatientThemesRead:
        themes = await self.repo.get_by_patient_id(patient_id)
        if not themes:
            raise NotFoundError(
                resource="PatientThemes",
                detail=f"No themes exist for patient {patient_id}",
            )
        return self._to_read(themes)

    @staticmethod
    def _format_recaps(recaps: list[Any]) -> str:
        lines: list[str] = []
        for idx, recap in enumerate(recaps, start=1):
            lines.append(f"--- SESSION {idx} ---")
            lines.append(f"Brief: {recap.brief}")
            if recap.key_topics:
                lines.append(f"Topics: {', '.join(recap.key_topics)}")
            if recap.emotional_tone:
                lines.append(f"Tone: {recap.emotional_tone}")
            if recap.homework_assigned:
                homework_strs = [
                    item.get("task", "")
                    for item in recap.homework_assigned
                    if isinstance(item, dict) and item.get("task")
                ]
                if homework_strs:
                    lines.append(f"Homework: {'; '.join(homework_strs)}")
            if recap.follow_ups:
                lines.append(f"Follow-ups: {'; '.join(recap.follow_ups)}")
            if recap.risk_flags:
                lines.append(f"Risk flags: {'; '.join(recap.risk_flags)}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _parse_payload(raw: str) -> PatientThemesPayload:
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
            logger.error("Failed to decode themes JSON: %s\nRaw: %s", exc, raw[:500])
            raise ThemesServiceError("LLM returned non-JSON output") from exc

        try:
            return PatientThemesPayload.model_validate(data)
        except PydanticValidationError as exc:
            logger.error("Themes payload failed validation: %s", exc)
            raise ThemesServiceError(f"LLM output did not match expected schema: {exc}") from exc

    @staticmethod
    def _to_read(themes: Any) -> PatientThemesRead:
        return PatientThemesRead(
            id=themes.id,
            patient_id=themes.patient_id,
            recurring_topics=[RecurringTopic(**t) for t in (themes.recurring_topics or [])],
            emotional_patterns=[EmotionalPattern(**p) for p in (themes.emotional_patterns or [])],
            coping_strategies=[CopingStrategy(**s) for s in (themes.coping_strategies or [])],
            progress_indicators=list(themes.progress_indicators or []),
            ongoing_concerns=list(themes.ongoing_concerns or []),
            source_session_count=themes.source_session_count,
            model_name=themes.model_name,
            generated_at=themes.generated_at,
            created_at=themes.created_at,
            updated_at=themes.updated_at,
        )
