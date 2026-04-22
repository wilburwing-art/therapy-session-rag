"""search_vectors — full-text search vectors for transcripts, recaps, sessions

Adds a Postgres ``tsvector`` column named ``search_vector`` to three tables
so therapists can answer "what session did we talk about X?" via Postgres
full-text search. Each column is a generated column (Postgres 12+) that the
database recomputes on every row write, and each gets its own GIN index.

- ``transcripts.search_vector`` = to_tsvector('english', full_text)
- ``session_recaps.search_vector`` = to_tsvector('english', brief || ' ' || jsonb key_topics concatenated)
- ``sessions.search_vector`` = to_tsvector('english', coalesce(therapist_notes, ''))

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-04-21 15:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add generated tsvector columns plus GIN indexes."""
    # transcripts.search_vector from full_text (always present, NOT NULL).
    op.execute(
        """
        ALTER TABLE transcripts
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', coalesce(full_text, ''))) STORED
        """
    )
    op.execute(
        "CREATE INDEX ix_transcripts_search_vector "
        "ON transcripts USING GIN (search_vector)"
    )

    # session_recaps.search_vector from brief plus key_topics. key_topics is
    # JSONB storing a JSON array of strings. Postgres generated columns must
    # use IMMUTABLE expressions, which rules out subqueries and
    # jsonb_array_elements_text. Casting the JSONB directly to text yields a
    # JSON-serialized array like ["sleep","anxiety"] — the FTS tokenizer
    # strips punctuation and picks up the meaningful words, which is what
    # we want for "did we talk about X" lookups.
    op.execute(
        """
        ALTER TABLE session_recaps
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector(
                'english',
                coalesce(brief, '') || ' ' || coalesce(key_topics::text, '')
            )
        ) STORED
        """
    )
    op.execute(
        "CREATE INDEX ix_session_recaps_search_vector "
        "ON session_recaps USING GIN (search_vector)"
    )

    # sessions.search_vector from therapist_notes (may be NULL).
    op.execute(
        """
        ALTER TABLE sessions
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', coalesce(therapist_notes, ''))) STORED
        """
    )
    op.execute(
        "CREATE INDEX ix_sessions_search_vector "
        "ON sessions USING GIN (search_vector)"
    )


def downgrade() -> None:
    """Drop GIN indexes and generated tsvector columns."""
    op.execute("DROP INDEX IF EXISTS ix_sessions_search_vector")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS search_vector")

    op.execute("DROP INDEX IF EXISTS ix_session_recaps_search_vector")
    op.execute("ALTER TABLE session_recaps DROP COLUMN IF EXISTS search_vector")

    op.execute("DROP INDEX IF EXISTS ix_transcripts_search_vector")
    op.execute("ALTER TABLE transcripts DROP COLUMN IF EXISTS search_vector")
