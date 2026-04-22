"""Recap-quality evaluation over synthetic transcript fixtures.

Hermetic: uses FakeClaudeClient (no API), bypasses DB by constructing
the same prompt the service would send and parsing the response with
SummarizationService._parse_payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.models.domain.session_recap import SessionRecapPayload
from src.services.claude_client import Message
from src.services.summarization_service import SYSTEM_PROMPT, SummarizationService
from tests.evaluation.conftest import FakeClaudeClient, TranscriptFixture

pytestmark = pytest.mark.evaluation


@dataclass
class RecapCheckResult:
    name: str
    passed: bool
    failures: list[str]


def _build_user_message(fixture: TranscriptFixture) -> str:
    """Match the prompt shape produced by SummarizationService.generate_recap.

    We include fixture.disclaimer so the FakeClaudeClient can route on it.
    """
    transcript_body = SummarizationService._format_transcript_for_prompt(
        full_text=fixture.full_text,
        segments=fixture.segments,
    )
    return (
        f"[{fixture.disclaimer}]\n"
        "Here is the full transcript of a therapy session. "
        "Produce the JSON recap per the system instructions.\n\n"
        "TRANSCRIPT:\n"
        f"{transcript_body}"
    )


async def _run_recap(
    fixture: TranscriptFixture,
    client: FakeClaudeClient,
) -> SessionRecapPayload:
    response = await client.chat(
        messages=[Message(role="user", content=_build_user_message(fixture))],
        system_prompt=SYSTEM_PROMPT,
        max_tokens=2048,
        temperature=0.2,
    )
    return SummarizationService._parse_payload(response.content)


def _check_expected(
    fixture: TranscriptFixture,
    payload: SessionRecapPayload,
) -> RecapCheckResult:
    """Apply the per-fixture assertions and collect failures."""
    expected: dict[str, Any] = fixture.expected_recap
    failures: list[str] = []

    # Brief length
    brief_len = len(payload.brief or "")
    if not (30 <= brief_len <= 2000):
        failures.append(f"brief length {brief_len} out of range [30, 2000]")

    # Key topics any-of
    wanted_topics = [t.lower() for t in expected.get("key_topics_any_of", [])]
    if wanted_topics:
        got = " ".join(payload.key_topics).lower()
        if not any(t in got for t in wanted_topics):
            failures.append(
                f"no expected topic in {payload.key_topics!r} "
                f"(wanted any of {wanted_topics!r})"
            )

    # Emotional tone contains any
    tone_pool = [s.lower() for s in expected.get("emotional_tone_contains_any", [])]
    tone = (payload.emotional_tone or "").lower()
    if tone_pool and tone and not any(p in tone for p in tone_pool):
        failures.append(
            f"emotional_tone {tone!r} does not contain any of {tone_pool!r}"
        )
    # If tone is None, skip per spec.

    # Risk flags polarity
    expect_risk = bool(expected.get("expected_risk_flags"))
    got_risk = bool(payload.risk_flags)
    if expect_risk != got_risk:
        failures.append(
            f"risk_flags polarity mismatch: expected={expect_risk}, got={got_risk} "
            f"({payload.risk_flags!r})"
        )

    # If risk expected, at least one flag contains a substring from the pool
    if expect_risk:
        subs = expected.get("risk_flag_substring_any") or []
        joined = " ".join(payload.risk_flags).lower()
        if subs and not any(s.lower() in joined for s in subs):
            failures.append(
                f"risk_flags {payload.risk_flags!r} "
                f"missing any of {subs!r}"
            )

    return RecapCheckResult(
        name=fixture.name,
        passed=not failures,
        failures=failures,
    )


# Module-scope counters so the aggregate test can report a rate after the
# per-fixture tests have run. pytest runs tests in file order, so the
# aggregate runs last.
_RECAP_STATS: dict[str, int] = {"passed": 0, "failed": 0}


async def test_recap_per_fixture(
    all_transcript_fixtures: list[TranscriptFixture],
    mock_claude_client: FakeClaudeClient,
) -> None:
    """Run recap evaluation for every fixture; collect failures."""
    failures_all: list[str] = []

    for fixture in all_transcript_fixtures:
        payload = await _run_recap(fixture, mock_claude_client)
        result = _check_expected(fixture, payload)
        if result.passed:
            _RECAP_STATS["passed"] += 1
        else:
            _RECAP_STATS["failed"] += 1
            failures_all.append(
                f"[{result.name}] " + "; ".join(result.failures)
            )

    assert not failures_all, (
        "Recap evaluation failures:\n  - " + "\n  - ".join(failures_all)
    )


async def test_recap_brief_length_range(
    all_transcript_fixtures: list[TranscriptFixture],
    mock_claude_client: FakeClaudeClient,
) -> None:
    """Every fixture gets a recap with brief length in range."""
    for fixture in all_transcript_fixtures:
        payload = await _run_recap(fixture, mock_claude_client)
        assert 30 <= len(payload.brief) <= 2000, (
            f"{fixture.name} brief length {len(payload.brief)}"
        )


async def test_recap_risk_fixture_sets_flag(
    all_transcript_fixtures: list[TranscriptFixture],
    mock_claude_client: FakeClaudeClient,
) -> None:
    """The SI-risk fixture must produce a risk flag containing expected text."""
    risk_fixture = next(
        (fx for fx in all_transcript_fixtures if "si_risk" in fx.name),
        None,
    )
    assert risk_fixture is not None, "expected transcript_si_risk.json fixture"

    payload = await _run_recap(risk_fixture, mock_claude_client)
    assert payload.risk_flags, "SI fixture must produce non-empty risk_flags"
    expected_subs = risk_fixture.expected_recap.get("risk_flag_substring_any", [])
    joined = " ".join(payload.risk_flags).lower()
    assert any(s.lower() in joined for s in expected_subs), (
        f"risk_flags {payload.risk_flags!r} missing any of {expected_subs!r}"
    )


async def test_recap_non_risk_fixtures_no_flags(
    all_transcript_fixtures: list[TranscriptFixture],
    mock_claude_client: FakeClaudeClient,
) -> None:
    """Non-risk fixtures must not produce risk flags."""
    non_risk = [
        fx for fx in all_transcript_fixtures
        if not fx.expected_recap.get("expected_risk_flags")
    ]
    assert non_risk, "at least one non-risk fixture expected"

    for fx in non_risk:
        payload = await _run_recap(fx, mock_claude_client)
        assert not payload.risk_flags, (
            f"{fx.name} should have no risk_flags, got {payload.risk_flags!r}"
        )


def test_recap_aggregate_pass_rate() -> None:
    """Print aggregate recap pass rate for visibility and assert 100%."""
    total = _RECAP_STATS["passed"] + _RECAP_STATS["failed"]
    if total == 0:
        pytest.skip("test_recap_per_fixture did not run")
    rate = _RECAP_STATS["passed"] / total
    print(
        f"\n[recap-eval] passed {_RECAP_STATS['passed']}/{total} "
        f"({rate:.0%})"
    )
    assert rate == 1.0, f"recap pass rate {rate:.0%} < 100%"
