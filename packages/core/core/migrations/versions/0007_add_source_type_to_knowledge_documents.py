"""Add source_type to knowledge_documents for cleaning rule selection

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_documents") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_type",
                sa.String(20),
                nullable=False,
                server_default="rulebook",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("knowledge_documents") as batch_op:
        batch_op.drop_column("source_type")
