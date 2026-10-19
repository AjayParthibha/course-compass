"""student approvals

Revision ID: c3f1a9d2e7b4
Revises: abc806d6f386
Create Date: 2026-10-19 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f1a9d2e7b4"
down_revision: str | Sequence[str] | None = "abc806d6f386"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("students", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("approvals", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("students", schema=None) as batch_op:
        batch_op.drop_column("approvals")
