"""Allow one active share link per file.

Revision ID: 4d5e6f7a8b9c
Revises: 3c4d5e6f7a8b
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4d5e6f7a8b9c"
down_revision: Union[str, Sequence[str], None] = "3c4d5e6f7a8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH ranked_shares AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY file_id
                           ORDER BY created_at DESC, id DESC
                       ) AS position
                FROM shares
                WHERE revoked_at IS NULL
            )
            UPDATE shares
            SET revoked_at = now()
            FROM ranked_shares
            WHERE shares.id = ranked_shares.id
              AND ranked_shares.position > 1
            """
        )
    )
    op.create_index(
        "uq_shares_one_active_per_file",
        "shares",
        ["file_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_shares_one_active_per_file", table_name="shares")
