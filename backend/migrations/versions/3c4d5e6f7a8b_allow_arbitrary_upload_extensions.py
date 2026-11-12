"""Allow arbitrary file extension lengths.

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7a
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3c4d5e6f7a8b"
down_revision: Union[str, Sequence[str], None] = "2b3c4d5e6f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "files",
        "extension",
        existing_type=sa.String(length=10),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "upload_sessions",
        "extension",
        existing_type=sa.String(length=10),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "upload_sessions",
        "extension",
        existing_type=sa.String(length=255),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
    op.alter_column(
        "files",
        "extension",
        existing_type=sa.String(length=255),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
