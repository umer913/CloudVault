"""Use backend-only RLS configuration.

Revision ID: 1a2b3c4d5e6f
Revises: 0e874da7372c
"""

from typing import Sequence, Union

from alembic import op


revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "0e874da7372c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table, policy in (
        ("shares", "shares_own_data"),
        ("files", "files_own_data"),
        ("folders", "folders_own_data"),
        ("users", "users_own_data"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in ("users", "folders", "files", "shares"):
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
