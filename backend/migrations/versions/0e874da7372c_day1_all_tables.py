
"""day1 all tables

Revision ID: 0e874da7372c
Revises:
Create Date: 2026-11-03 17:16:27.778318
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Revision identifiers
revision: str = "0e874da7372c"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial database schema."""

    # 1. USERS TABLE
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "storage_quota",
            sa.BigInteger(),
            server_default="2000000000",
            nullable=False
        ),
        sa.Column(
            "used_bytes",
            sa.BigInteger(),
            server_default="0",
            nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),
        sa.CheckConstraint(
            "storage_quota >= 0",
            name="ck_users_quota_nonneg"
        ),
        sa.CheckConstraint(
            "used_bytes >= 0",
            name="ck_users_used_nonneg"
        ),
        sa.CheckConstraint(
            "used_bytes <= storage_quota",
            name="ck_users_storage_limit"
        ),
        sa.UniqueConstraint("email")
    )

    # 2. FOLDERS TABLE
    op.create_table(
        "folders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id != id",
            name="ck_folders_no_self_parent"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"]
        ),
        sa.ForeignKeyConstraint(
            ["parent_id", "user_id"],
            ["folders.id", "folders.user_id"],
            name="fk_folders_parent_owner"
        ),
        sa.UniqueConstraint(
            "id",
            "user_id",
            name="uq_folders_id_user"
        )
    )

    op.create_index(
        "ix_folders_user_parent",
        "folders",
        ["user_id", "parent_id"]
    )

    op.create_index(
        "uq_folders_child",
        "folders",
        ["user_id", "parent_id", "name"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NOT NULL")
    )

    op.create_index(
        "uq_folders_root",
        "folders",
        ["user_id", "name"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NULL")
    )

    # 3. FILES TABLE
    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("folder_id", sa.Integer(), nullable=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("extension", sa.String(10), nullable=False),
        sa.Column("storage_key", sa.String(64), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(150), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),
        sa.CheckConstraint(
            "size >= 0",
            name="ck_files_size_nonneg"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"]
        ),
        sa.ForeignKeyConstraint(
            ["folder_id", "user_id"],
            ["folders.id", "folders.user_id"],
            name="fk_files_folder_owner"
        ),
        sa.UniqueConstraint("storage_key")
    )

    op.create_index(
        "ix_files_user_created",
        "files",
        ["user_id", sa.literal_column("created_at DESC")]
    )

    op.create_index(
        "ix_files_user_folder",
        "files",
        ["user_id", "folder_id"]
    )

    op.create_index(
        "uq_files_child",
        "files",
        ["user_id", "folder_id", "original_name"],
        unique=True,
        postgresql_where=sa.text("folder_id IS NOT NULL")
    )

    op.create_index(
        "uq_files_root",
        "files",
        ["user_id", "original_name"],
        unique=True,
        postgresql_where=sa.text("folder_id IS NULL")
    )

    # 4. SHARES TABLE
    op.create_table(
        "shares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("permission", sa.String(10), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),
        sa.CheckConstraint(
            "permission IN ('view', 'download')",
            name="ck_shares_permission"
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            ondelete="CASCADE"
        ),
        sa.UniqueConstraint("token_hash")
    )

    op.create_index(
        "ix_shares_file",
        "shares",
        ["file_id"]
    )

    # 5. ENABLE ROW LEVEL SECURITY
    tables = ("users", "folders", "files", "shares")

    for table in tables:
        op.execute(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"
        )
        op.execute(
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"
        )

    # 6. RLS POLICIES
    # The application must set app.user_id securely
    # inside each transaction.

    op.execute("""
        CREATE POLICY users_own_data
        ON users
        FOR ALL
        USING (
            id = NULLIF(
                current_setting('app.user_id', true), ''
            )::integer
        )
        WITH CHECK (
            id = NULLIF(
                current_setting('app.user_id', true), ''
            )::integer
        )
    """)

    op.execute("""
        CREATE POLICY folders_own_data
        ON folders
        FOR ALL
        USING (
            user_id = NULLIF(
                current_setting('app.user_id', true), ''
            )::integer
        )
        WITH CHECK (
            user_id = NULLIF(
                current_setting('app.user_id', true), ''
            )::integer
        )
    """)

    op.execute("""
        CREATE POLICY files_own_data
        ON files
        FOR ALL
        USING (
            user_id = NULLIF(
                current_setting('app.user_id', true), ''
            )::integer
        )
        WITH CHECK (
            user_id = NULLIF(
                current_setting('app.user_id', true), ''
            )::integer
        )
    """)

    op.execute("""
        CREATE POLICY shares_own_data
        ON shares
        FOR ALL
        USING (
            EXISTS (
                SELECT 1
                FROM files
                WHERE files.id = shares.file_id
                AND files.user_id = NULLIF(
                    current_setting('app.user_id', true), ''
                )::integer
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1
                FROM files
                WHERE files.id = shares.file_id
                AND files.user_id = NULLIF(
                    current_setting('app.user_id', true), ''
                )::integer
            )
        )
    """)


def downgrade() -> None:
    """Reverse database schema changes."""

    # Drop policies first
    op.execute("DROP POLICY IF EXISTS shares_own_data ON shares")
    op.execute("DROP POLICY IF EXISTS files_own_data ON files")
    op.execute("DROP POLICY IF EXISTS folders_own_data ON folders")
    op.execute("DROP POLICY IF EXISTS users_own_data ON users")

    # Disable RLS before dropping tables
    for table in ("shares", "files", "folders", "users"):
        op.execute(
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"
        )
        op.execute(
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"
        )

    # Drop tables in reverse dependency order
    op.drop_index("ix_shares_file", table_name="shares")
    op.drop_table("shares")

    op.drop_index("uq_files_root", table_name="files")
    op.drop_index("uq_files_child", table_name="files")
    op.drop_index("ix_files_user_folder", table_name="files")
    op.drop_index("ix_files_user_created", table_name="files")
    op.drop_table("files")

    op.drop_index("uq_folders_root", table_name="folders")
    op.drop_index("uq_folders_child", table_name="folders")
    op.drop_index("ix_folders_user_parent", table_name="folders")
    op.drop_table("folders")

    op.drop_table("users")
