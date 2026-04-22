"""Service for rendering therapy-practice PDFs.

Produces styled, letter-size PDFs for clinical workflows:
- Session recap (one session)
- Patient record (cover, per-session recaps, themes, assessment trend)
- Patient themes (themes-only document)

The output bytes are returned directly to the caller, which is responsible
for wrapping them in a StreamingResponse. All org-scope checks load entities
via existing repos/queries and reject mismatches with ForbiddenError.
"""

from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenError, NotFoundError
from src.models.db.assessment import Assessment
from src.models.db.organization import Organization
from src.models.db.patient_themes import PatientThemes
from src.models.db.session import Session as SessionRecording
from src.models.db.session_recap import SessionRecap
from src.models.db.user import User, UserRole
from src.repositories.patient_themes_repo import PatientThemesRepository
from src.repositories.session_recap_repo import SessionRecapRepository
from src.repositories.session_repo import SessionRepository

logger = logging.getLogger(__name__)


class PdfService:
    """Render clinical PDFs for therapist-facing documentation."""

    MARGIN = 1.0 * inch
    PAGE_SIZE = letter

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.session_repo = SessionRepository(db_session)
        self.recap_repo = SessionRecapRepository(db_session)
        self.themes_repo = PatientThemesRepository(db_session)

    # ----- Public API -----

    async def render_session_recap_pdf(
        self,
        session_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> bytes:
        """Render a single-session recap PDF.

        Raises:
            NotFoundError: session or recap missing.
            ForbiddenError: session's org does not match organization_id.
        """
        session = await self._load_session_in_org(session_id, organization_id)
        recap = await self.recap_repo.get_by_session_id(session_id)
        if recap is None:
            raise NotFoundError(
                resource="SessionRecap",
                detail=f"No recap exists for session {session_id}",
            )

        patient = await self._get_user(session.patient_id)
        therapist = await self._get_user(session.therapist_id)
        practice_name = await self._get_practice_name(organization_id)

        flowables = self._build_recap_flowables(
            session=session,
            recap=recap,
            patient=patient,
            therapist=therapist,
        )
        return self._render(flowables, practice_name=practice_name)

    async def render_patient_record_pdf(
        self,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> bytes:
        """Render a multi-page patient record PDF.

        Layout: cover page, per-session recap pages, themes page, assessment
        trend table. Missing sections render a short placeholder rather
        than being skipped so the document structure stays predictable.
        """
        patient = await self._load_patient_in_org(patient_id, organization_id)
        practice_name = await self._get_practice_name(organization_id)

        sessions = await self._list_sessions_for_patient(patient_id)
        session_ids = [s.id for s in sessions]
        recaps_by_session = await self._recaps_by_session(session_ids)
        themes = await self.themes_repo.get_by_patient_id(patient_id)
        assessments = await self._list_assessments_for_patient(patient_id)

        styles = self._styles()
        flowables: list[Any] = []

        # Cover page
        flowables.append(Paragraph("Patient Record", styles["PdfTitle"]))
        flowables.append(Spacer(1, 0.25 * inch))
        flowables.append(
            Paragraph(
                _escape(patient.full_name or patient.email),
                styles["PdfHeading"],
            )
        )
        flowables.append(
            Paragraph(_escape(patient.email), styles["PdfBody"])
        )
        flowables.append(Spacer(1, 0.15 * inch))
        flowables.append(
            Paragraph(
                f"Sessions on file: {len(sessions)} &middot; "
                f"Recaps: {len(recaps_by_session)} &middot; "
                f"Assessments: {len(assessments)}",
                styles["PdfBrief"],
            )
        )
        flowables.append(
            Paragraph(
                f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
                styles["PdfBrief"],
            )
        )

        # Per-session recap pages
        for session in sessions:
            flowables.append(PageBreak())
            recap = recaps_by_session.get(session.id)
            flowables.extend(
                self._session_recap_section(session=session, recap=recap, styles=styles)
            )

        # Themes page
        flowables.append(PageBreak())
        flowables.append(Paragraph("Cross-session themes", styles["PdfTitle"]))
        flowables.append(Spacer(1, 0.15 * inch))
        if themes is None:
            flowables.append(
                Paragraph(
                    "No themes have been synthesized for this patient.",
                    styles["PdfBody"],
                )
            )
        else:
            flowables.extend(self._themes_flowables(themes, styles))

        # Assessment trend table
        flowables.append(PageBreak())
        flowables.append(Paragraph("Assessment trend", styles["PdfTitle"]))
        flowables.append(Spacer(1, 0.15 * inch))
        flowables.extend(self._assessment_table(assessments, styles))

        return self._render(flowables, practice_name=practice_name)

    async def render_themes_pdf(
        self,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> bytes:
        """Render a themes-only PDF.

        Raises:
            NotFoundError: no themes exist for the patient.
            ForbiddenError: patient's org does not match organization_id.
        """
        patient = await self._load_patient_in_org(patient_id, organization_id)
        themes = await self.themes_repo.get_by_patient_id(patient_id)
        if themes is None:
            raise NotFoundError(
                resource="PatientThemes",
                detail=f"No themes exist for patient {patient_id}",
            )
        practice_name = await self._get_practice_name(organization_id)

        styles = self._styles()
        flowables: list[Any] = [
            Paragraph("Patient themes", styles["PdfTitle"]),
            Spacer(1, 0.1 * inch),
            Paragraph(
                _escape(patient.full_name or patient.email),
                styles["PdfHeading"],
            ),
            Paragraph(
                f"Synthesized from {themes.source_session_count} session recap(s)",
                styles["PdfBrief"],
            ),
            Spacer(1, 0.2 * inch),
        ]
        flowables.extend(self._themes_flowables(themes, styles))
        return self._render(flowables, practice_name=practice_name)

    # ----- Org-scope helpers -----

    async def _load_session_in_org(
        self,
        session_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> SessionRecording:
        session = await self.session_repo.get_by_id(session_id)
        if session is None:
            raise NotFoundError(resource="Session", resource_id=str(session_id))
        # Patient and therapist must both be in the caller's org.
        patient = await self._get_user(session.patient_id)
        therapist = await self._get_user(session.therapist_id)
        if (
            patient.organization_id != organization_id
            or therapist.organization_id != organization_id
        ):
            raise ForbiddenError(
                detail="Session does not belong to your organization"
            )
        return session

    async def _load_patient_in_org(
        self,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> User:
        result = await self.db_session.execute(
            select(User).where(User.id == patient_id)
        )
        patient = result.scalar_one_or_none()
        if patient is None or patient.role != UserRole.PATIENT:
            raise NotFoundError(resource="Patient", resource_id=str(patient_id))
        if patient.organization_id != organization_id:
            raise ForbiddenError(
                detail="Patient does not belong to your organization"
            )
        return patient

    async def _get_user(self, user_id: uuid.UUID) -> User:
        result = await self.db_session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError(resource="User", resource_id=str(user_id))
        return user

    async def _get_practice_name(self, organization_id: uuid.UUID) -> str:
        result = await self.db_session.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        org = result.scalar_one_or_none()
        if org is None:
            return "Unknown Practice"
        return org.name

    async def _list_sessions_for_patient(
        self,
        patient_id: uuid.UUID,
    ) -> list[SessionRecording]:
        result = await self.db_session.execute(
            select(SessionRecording)
            .where(SessionRecording.patient_id == patient_id)
            .order_by(SessionRecording.session_date.asc())
        )
        return list(result.scalars().all())

    async def _recaps_by_session(
        self,
        session_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, SessionRecap]:
        if not session_ids:
            return {}
        result = await self.db_session.execute(
            select(SessionRecap).where(SessionRecap.session_id.in_(session_ids))
        )
        return {r.session_id: r for r in result.scalars().all()}

    async def _list_assessments_for_patient(
        self,
        patient_id: uuid.UUID,
    ) -> list[Assessment]:
        result = await self.db_session.execute(
            select(Assessment)
            .where(Assessment.patient_id == patient_id)
            .order_by(Assessment.administered_at.asc())
        )
        return list(result.scalars().all())

    # ----- Flowable builders -----

    @staticmethod
    def _styles() -> dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        return {
            "PdfTitle": ParagraphStyle(
                name="PdfTitle",
                parent=base["Title"],
                fontSize=20,
                leading=24,
                spaceAfter=8,
            ),
            "PdfHeading": ParagraphStyle(
                name="PdfHeading",
                parent=base["Heading2"],
                fontSize=14,
                leading=18,
                spaceBefore=6,
                spaceAfter=4,
            ),
            "PdfSubheading": ParagraphStyle(
                name="PdfSubheading",
                parent=base["Heading3"],
                fontSize=11,
                leading=14,
                textColor=colors.HexColor("#334155"),
                spaceBefore=8,
                spaceAfter=2,
            ),
            "PdfBody": ParagraphStyle(
                name="PdfBody",
                parent=base["BodyText"],
                fontSize=10,
                leading=14,
                spaceAfter=6,
            ),
            "PdfBrief": ParagraphStyle(
                name="PdfBrief",
                parent=base["BodyText"],
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#475569"),
                spaceAfter=4,
            ),
            "PdfRisk": ParagraphStyle(
                name="PdfRisk",
                parent=base["BodyText"],
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#991b1b"),
                spaceAfter=4,
            ),
        }

    def _build_recap_flowables(
        self,
        session: SessionRecording,
        recap: SessionRecap,
        patient: User,
        therapist: User,
    ) -> list[Any]:
        styles = self._styles()
        items: list[Any] = []

        items.append(Paragraph("Session recap", styles["PdfTitle"]))
        items.append(
            Paragraph(
                _escape(patient.full_name or patient.email),
                styles["PdfHeading"],
            )
        )
        items.append(
            Paragraph(
                "Therapist: "
                + _escape(therapist.full_name or therapist.email),
                styles["PdfBrief"],
            )
        )
        items.append(
            Paragraph(
                "Session date: "
                + session.session_date.strftime("%Y-%m-%d %H:%M"),
                styles["PdfBrief"],
            )
        )
        items.append(Spacer(1, 0.2 * inch))

        items.extend(self._recap_body(recap, styles))
        return items

    def _session_recap_section(
        self,
        session: SessionRecording,
        recap: SessionRecap | None,
        styles: dict[str, ParagraphStyle],
    ) -> list[Any]:
        items: list[Any] = []
        items.append(
            Paragraph(
                "Session on "
                + session.session_date.strftime("%Y-%m-%d %H:%M"),
                styles["PdfTitle"],
            )
        )
        items.append(
            Paragraph(
                f"Status: {_status_value(session.status)}",
                styles["PdfBrief"],
            )
        )
        items.append(Spacer(1, 0.15 * inch))
        if recap is None:
            items.append(
                Paragraph(
                    "No recap generated for this session.",
                    styles["PdfBody"],
                )
            )
            return items
        items.extend(self._recap_body(recap, styles))
        return items

    @staticmethod
    def _recap_body(
        recap: SessionRecap,
        styles: dict[str, ParagraphStyle],
    ) -> list[Any]:
        items: list[Any] = []
        items.append(Paragraph("Brief", styles["PdfSubheading"]))
        items.append(Paragraph(_escape(recap.brief or ""), styles["PdfBody"]))

        if recap.emotional_tone:
            items.append(
                Paragraph(
                    "Emotional tone: " + _escape(recap.emotional_tone),
                    styles["PdfBrief"],
                )
            )

        if recap.key_topics:
            items.append(Paragraph("Key topics", styles["PdfSubheading"]))
            items.append(
                Paragraph(
                    ", ".join(_escape(t) for t in recap.key_topics),
                    styles["PdfBody"],
                )
            )

        if recap.homework_assigned:
            items.append(Paragraph("Homework assigned", styles["PdfSubheading"]))
            for raw in recap.homework_assigned:
                if not isinstance(raw, dict):
                    continue
                task = str(raw.get("task") or "").strip()
                if not task:
                    continue
                notes = str(raw.get("notes") or "").strip()
                text = _escape(task)
                if notes:
                    text += " &mdash; " + _escape(notes)
                items.append(Paragraph("&bull; " + text, styles["PdfBody"]))

        if recap.follow_ups:
            items.append(Paragraph("Follow-ups", styles["PdfSubheading"]))
            for f in recap.follow_ups:
                items.append(
                    Paragraph("&bull; " + _escape(str(f)), styles["PdfBody"])
                )

        if recap.risk_flags:
            items.append(Paragraph("Risk flags for review", styles["PdfSubheading"]))
            for r in recap.risk_flags:
                items.append(
                    Paragraph("&bull; " + _escape(str(r)), styles["PdfRisk"])
                )

        return items

    @staticmethod
    def _themes_flowables(
        themes: PatientThemes,
        styles: dict[str, ParagraphStyle],
    ) -> list[Any]:
        items: list[Any] = []

        items.append(Paragraph("Recurring topics", styles["PdfSubheading"]))
        if themes.recurring_topics:
            for raw in themes.recurring_topics:
                if not isinstance(raw, dict):
                    continue
                topic = _escape(str(raw.get("topic") or ""))
                count = raw.get("session_count")
                summary = raw.get("summary")
                line = f"&bull; <b>{topic}</b>"
                if isinstance(count, int):
                    line += f" &mdash; {count} session(s)"
                if isinstance(summary, str) and summary.strip():
                    line += f": {_escape(summary)}"
                items.append(Paragraph(line, styles["PdfBody"]))
        else:
            items.append(Paragraph("None identified.", styles["PdfBody"]))

        items.append(Paragraph("Emotional patterns", styles["PdfSubheading"]))
        if themes.emotional_patterns:
            for raw in themes.emotional_patterns:
                if not isinstance(raw, dict):
                    continue
                pattern = _escape(str(raw.get("pattern") or ""))
                evidence = raw.get("evidence")
                line = f"&bull; <b>{pattern}</b>"
                if isinstance(evidence, str) and evidence.strip():
                    line += f": {_escape(evidence)}"
                items.append(Paragraph(line, styles["PdfBody"]))
        else:
            items.append(Paragraph("None noted.", styles["PdfBody"]))

        items.append(Paragraph("Coping strategies", styles["PdfSubheading"]))
        if themes.coping_strategies:
            for raw in themes.coping_strategies:
                if not isinstance(raw, dict):
                    continue
                strategy = _escape(str(raw.get("strategy") or ""))
                notes = raw.get("notes")
                line = f"&bull; <b>{strategy}</b>"
                if isinstance(notes, str) and notes.strip():
                    line += f": {_escape(notes)}"
                items.append(Paragraph(line, styles["PdfBody"]))
        else:
            items.append(Paragraph("None discussed.", styles["PdfBody"]))

        items.append(Paragraph("Progress indicators", styles["PdfSubheading"]))
        if themes.progress_indicators:
            for p in themes.progress_indicators:
                items.append(
                    Paragraph("&bull; " + _escape(str(p)), styles["PdfBody"])
                )
        else:
            items.append(Paragraph("None noted.", styles["PdfBody"]))

        items.append(Paragraph("Ongoing concerns", styles["PdfSubheading"]))
        if themes.ongoing_concerns:
            for c in themes.ongoing_concerns:
                items.append(
                    Paragraph("&bull; " + _escape(str(c)), styles["PdfBody"])
                )
        else:
            items.append(Paragraph("None.", styles["PdfBody"]))

        return items

    @staticmethod
    def _assessment_table(
        assessments: list[Assessment],
        styles: dict[str, ParagraphStyle],
    ) -> list[Any]:
        if not assessments:
            return [
                Paragraph(
                    "No assessments on file for this patient.",
                    styles["PdfBody"],
                )
            ]
        header = ["Date", "Instrument", "Score", "Severity"]
        rows: list[list[str]] = [header]
        for a in assessments:
            rows.append(
                [
                    a.administered_at.strftime("%Y-%m-%d"),
                    _instrument_value(a.instrument).upper(),
                    str(a.total_score),
                    a.severity or "",
                ]
            )
        table = Table(rows, hAlign="LEFT", repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.25,
                        colors.HexColor("#CBD5E1"),
                    ),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        return [table]

    # ----- Rendering pipeline -----

    def _render(
        self,
        flowables: list[Any],
        practice_name: str,
    ) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=self.PAGE_SIZE,
            leftMargin=self.MARGIN,
            rightMargin=self.MARGIN,
            topMargin=self.MARGIN,
            bottomMargin=self.MARGIN,
            title="TherapyRAG document",
            author=practice_name,
        )

        def on_page(canvas: Any, _doc: Any) -> None:
            _draw_header_footer(canvas, practice_name=practice_name)

        doc.build(flowables, onFirstPage=on_page, onLaterPages=on_page)
        return buffer.getvalue()


# ----- Module-level helpers (stateless) -----


def _draw_header_footer(canvas: Any, practice_name: str) -> None:
    """Draw per-page header + footer. Called by SimpleDocTemplate."""
    canvas.saveState()
    width, height = letter
    header_y = height - 0.5 * inch
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(colors.HexColor("#0F172A"))
    canvas.drawString(PdfService.MARGIN, header_y, "TherapyRAG")
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#475569"))
    canvas.drawRightString(
        width - PdfService.MARGIN,
        header_y,
        practice_name,
    )
    canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
    canvas.setLineWidth(0.3)
    canvas.line(
        PdfService.MARGIN,
        header_y - 4,
        width - PdfService.MARGIN,
        header_y - 4,
    )

    page_number = getattr(canvas, "_pageNumber", getattr(canvas, "getPageNumber", lambda: 1)())
    if callable(page_number):
        page_number = page_number()
    footer_y = 0.5 * inch
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawRightString(
        width - PdfService.MARGIN,
        footer_y,
        f"Page {page_number}",
    )
    canvas.restoreState()


def _escape(text: str) -> str:
    """HTML-escape for Paragraph markup. Paragraph uses a mini HTML parser."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _status_value(status: Any) -> str:
    """Best-effort render of a status enum or string."""
    value = getattr(status, "value", status)
    return str(value)


def _instrument_value(instrument: Any) -> str:
    value = getattr(instrument, "value", instrument)
    return str(value)
