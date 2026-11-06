"""Add persistent direct upload sessions.

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2b3c4d5e6f7a"
down_revision: Union[str, Sequence[str], None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(64), nullable=False),
        sa.Column("provider_upload_id", sa.String(255), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("extension", sa.String(10), nullable=False),
        sa.Column("mime_type", sa.String(150), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("folder_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'completing', 'completed', 'aborted', 'expired')",
            name="ck_upload_sessions_status",
        ),
        sa.CheckConstraint("size > 0", name="ck_upload_sessions_size_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["folder_id"], ["folders.id"]),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_upload_sessions_status_expires",
        "upload_sessions",
        ["status", "expires_at"],
    )
    op.create_index("ix_upload_sessions_user", "upload_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_upload_sessions_user", table_name="upload_sessions")
    op.drop_index(
        "ix_upload_sessions_status_expires",
        table_name="upload_sessions",
    )
    op.drop_table("upload_sessions")
