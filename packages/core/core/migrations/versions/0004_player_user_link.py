"""Add user_id FK to players table and update uniqueness constraint

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # recreate="always" drops and rebuilds the table, which also drops
    # the expression-based ix_players_campaign_player_name_lower index that
    # SQLite cannot reflect. The new ix_players_campaign_user index is added
    # in the rebuilt table.
    with op.batch_alter_table("players", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_players_user_id",
            "users",
            ["user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_players_campaign_user",
            ["campaign_id", "user_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("players", recreate="always") as batch_op:
        batch_op.drop_index("ix_players_campaign_user")
        batch_op.drop_constraint("fk_players_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")
