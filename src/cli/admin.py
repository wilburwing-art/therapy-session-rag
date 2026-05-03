"""``therapyrag-admin`` — operator CLI for SOC 2 / HIPAA flows.

Subcommands:
    access-review     List every admin user with last-login + dormancy.
    retention-purge   Delete analytics events older than the retention
                      horizon (default 7 years), preserving
                      ``retain_forever`` rows.

Dispatch is plain argparse — the script is rarely invoked, doesn't run
in the hot path, and the Click / Typer surface area was overkill for
two subcommands.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, TextIO

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import get_settings
from src.core.database import create_engine, create_session_factory
from src.models.db.event import AnalyticsEvent
from src.models.db.organization import Organization
from src.models.db.user import User, UserRole

if TYPE_CHECKING:
    pass


DORMANCY_THRESHOLD_DAYS = 90
RETENTION_DEFAULT_DAYS = 365 * 7  # 7 years per HIPAA guidance


@dataclass
class AdminRow:
    """Row shape for the access-review report."""

    user_id: uuid.UUID
    email: str
    full_name: str | None
    organization_name: str
    last_login_at: datetime | None
    dormant: bool


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="therapyrag-admin",
        description="Operator tooling for TherapyRAG (access reviews, retention purges).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # access-review
    ar = subparsers.add_parser(
        "access-review",
        help="List every admin user with last-login timestamp + dormancy flag.",
    )
    ar.add_argument(
        "--organization-id",
        type=str,
        default=None,
        help="Filter to a single organization by UUID.",
    )
    ar.add_argument(
        "--csv",
        action="store_true",
        help="Write CSV to stdout instead of a plain-text table.",
    )

    # retention-purge
    rp = subparsers.add_parser(
        "retention-purge",
        help="Delete analytics_events older than the retention horizon.",
    )
    rp.add_argument(
        "--days",
        type=int,
        default=RETENTION_DEFAULT_DAYS,
        help=(
            "Retention window in days (default: 7 years). Rows older than "
            "now - <days> are eligible for purging, except those marked "
            "retain_forever=true."
        ),
    )
    rp.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the row count that would be deleted and exit.",
    )

    return parser


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    settings = get_settings()
    engine = create_engine(settings)
    return create_session_factory(engine)


async def _collect_admin_rows(
    session: AsyncSession,
    organization_id: uuid.UUID | None,
) -> list[AdminRow]:
    """Build one AdminRow per admin user.

    Joins users -> organizations for display, then fetches the most
    recent ``auth.login_succeeded`` event per admin in a single grouped
    query. Dormancy is "no login in DORMANCY_THRESHOLD_DAYS days" —
    never-logged-in counts as dormant.
    """
    stmt = (
        select(User, Organization.name)
        .join(Organization, Organization.id == User.organization_id)
        .where(User.role == UserRole.ADMIN)
        .order_by(User.email.asc())
    )
    if organization_id is not None:
        stmt = stmt.where(User.organization_id == organization_id)
    users_result = await session.execute(stmt)
    users_with_org = list(users_result.all())

    if not users_with_org:
        return []

    admin_ids = [user.id for user, _ in users_with_org]
    login_stmt = (
        select(
            AnalyticsEvent.actor_id,
            func.max(AnalyticsEvent.event_timestamp).label("last_login"),
        )
        .where(
            and_(
                AnalyticsEvent.event_name == "auth.login_succeeded",
                AnalyticsEvent.actor_id.in_(admin_ids),
            )
        )
        .group_by(AnalyticsEvent.actor_id)
    )
    login_rows = (await session.execute(login_stmt)).all()
    last_login_by_user: dict[uuid.UUID, datetime] = {
        row.actor_id: row.last_login for row in login_rows if row.actor_id is not None
    }

    now = datetime.now(UTC)
    dormancy_cutoff = now - timedelta(days=DORMANCY_THRESHOLD_DAYS)

    out: list[AdminRow] = []
    for user, org_name in users_with_org:
        last_login = last_login_by_user.get(user.id)
        dormant = last_login is None or last_login < dormancy_cutoff
        out.append(
            AdminRow(
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                organization_name=org_name,
                last_login_at=last_login,
                dormant=dormant,
            )
        )
    return out


def _format_iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt is not None else ""


def _render_csv(rows: list[AdminRow], stream: TextIO) -> None:
    writer = csv.writer(stream)
    writer.writerow(["email", "full_name", "organization", "last_login_at", "dormant"])
    for row in rows:
        writer.writerow(
            [
                row.email,
                row.full_name or "",
                row.organization_name,
                _format_iso(row.last_login_at),
                "true" if row.dormant else "false",
            ]
        )


def _render_table(rows: list[AdminRow], stream: TextIO) -> None:
    if not rows:
        stream.write("No admin users found.\n")
        return
    headers = ("email", "full_name", "organization", "last_login_at", "dormant")
    data = [
        (
            row.email,
            row.full_name or "",
            row.organization_name,
            _format_iso(row.last_login_at) or "never",
            "yes" if row.dormant else "no",
        )
        for row in rows
    ]
    widths = [
        max(len(str(cell)) for cell in (header, *col))
        for header, col in zip(headers, zip(*data, strict=False), strict=False)
    ]
    sep = "  "
    stream.write(sep.join(h.ljust(w) for h, w in zip(headers, widths, strict=True)) + "\n")
    stream.write(sep.join("-" * w for w in widths) + "\n")
    for row in data:
        stream.write(
            sep.join(str(cell).ljust(w) for cell, w in zip(row, widths, strict=True)) + "\n"
        )


async def _run_access_review(
    organization_id: str | None,
    as_csv: bool,
    stream: TextIO,
) -> int:
    org_uuid: uuid.UUID | None = None
    if organization_id is not None:
        try:
            org_uuid = uuid.UUID(organization_id)
        except ValueError:
            sys.stderr.write(f"--organization-id must be a UUID (got {organization_id!r})\n")
            return 2

    session_factory = _make_session_factory()
    async with session_factory() as session:
        rows = await _collect_admin_rows(session, org_uuid)

    if as_csv:
        _render_csv(rows, stream)
    else:
        _render_table(rows, stream)
    return 0


async def _run_retention_purge(days: int, dry_run: bool, stream: TextIO) -> int:
    if days <= 0:
        sys.stderr.write("--days must be positive\n")
        return 2

    cutoff = datetime.now(UTC) - timedelta(days=days)
    session_factory = _make_session_factory()
    async with session_factory() as session:
        # AnalyticsEvent doesn't mix in TimestampMixin — retention is
        # measured against event_timestamp (when the event happened), not
        # a row-ingest time.
        count_stmt = (
            select(func.count(AnalyticsEvent.id))
            .where(AnalyticsEvent.event_timestamp < cutoff)
            .where(AnalyticsEvent.retain_forever.is_(False))
        )
        eligible = int((await session.execute(count_stmt)).scalar_one() or 0)

        if dry_run:
            stream.write(
                f"[dry-run] Would delete {eligible} analytics_events rows "
                f"older than {cutoff.isoformat()} "
                f"(retain_forever=false).\n"
            )
            return 0

        if eligible == 0:
            stream.write("Nothing to purge.\n")
            return 0

        del_stmt = (
            delete(AnalyticsEvent)
            .where(AnalyticsEvent.event_timestamp < cutoff)
            .where(AnalyticsEvent.retain_forever.is_(False))
        )
        result = await session.execute(del_stmt)
        await session.commit()
        # CursorResult exposes rowcount when the driver supports it; for
        # asyncpg this is always populated on DELETE.
        deleted = getattr(result, "rowcount", None) or 0
        stream.write(
            f"Purged {deleted} analytics_events rows older than "
            f"{cutoff.isoformat()} (retain_forever=false).\n"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point invoked by the ``therapyrag-admin`` script."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "access-review":
        return asyncio.run(
            _run_access_review(
                organization_id=args.organization_id,
                as_csv=args.csv,
                stream=sys.stdout,
            )
        )
    if args.command == "retention-purge":
        return asyncio.run(
            _run_retention_purge(
                days=args.days,
                dry_run=args.dry_run,
                stream=sys.stdout,
            )
        )
    parser.error(f"Unknown command: {args.command}")
    return 2  # unreachable, parser.error exits


if __name__ == "__main__":
    raise SystemExit(main())
