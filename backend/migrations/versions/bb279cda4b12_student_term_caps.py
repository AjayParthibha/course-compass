"""student term caps

Revision ID: bb279cda4b12
Revises: e65e31f9918f
Create Date: 2026-10-15 14:18:02.986472

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bb279cda4b12"
down_revision: str | Sequence[str] | None = "e65e31f9918f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("students", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("term_caps", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("students", schema=None) as batch_op:
        batch_op.drop_column("term_caps")
