"""plan version parent

Revision ID: abc806d6f386
Revises: bb279cda4b12
Create Date: 2026-10-15 15:08:14.824690

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "abc806d6f386"
down_revision: str | Sequence[str] | None = "bb279cda4b12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("plan_versions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("parent_version", sa.Integer(), nullable=True))
    # existing history was linear
    op.execute("UPDATE plan_versions SET parent_version = version - 1 WHERE version > 1")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("plan_versions", schema=None) as batch_op:
        batch_op.drop_column("parent_version")
