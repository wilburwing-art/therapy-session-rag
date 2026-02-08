"""add_video_chat_support

Revision ID: 26cb062ab77b
Revises: 014f56a4df24
Create Date: 2026-02-08 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '26cb062ab77b'
down_revision: Union[str, Sequence[str], None] = '014f56a4df24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add video chat support columns."""
    # Add video_chat_enabled to organizations
    op.add_column(
        'organizations',
        sa.Column('video_chat_enabled', sa.Boolean(), nullable=False, server_default='false')
    )

    # Create session_type enum
    session_type_enum = sa.Enum('upload', 'video_call', name='session_type')
    session_type_enum.create(op.get_bind(), checkfirst=True)

    # Add session_type to sessions
    op.add_column(
        'sessions',
        sa.Column(
            'session_type',
            sa.Enum('upload', 'video_call', name='session_type'),
            nullable=False,
            server_default='upload'
        )
    )


def downgrade() -> None:
    """Remove video chat support columns."""
    # Remove session_type column
    op.drop_column('sessions', 'session_type')

    # Drop session_type enum
    sa.Enum(name='session_type').drop(op.get_bind(), checkfirst=True)

    # Remove video_chat_enabled column
    op.drop_column('organizations', 'video_chat_enabled')
