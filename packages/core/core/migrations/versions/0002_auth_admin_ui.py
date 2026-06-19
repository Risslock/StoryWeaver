"""Auth & Admin UI — users, players, owner_id on campaigns, case-insensitive indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-19

Up steps (in order):
  1.  Create users table
  2.  Insert system user backfill record
  3.  Add owner_id nullable column to campaigns
  4.  UPDATE campaigns SET owner_id = system_user_id
  5.  Batch-alter owner_id to NOT NULL
  6.  Batch-alter join_code from String(8) to String(6)
  7.  Add ix_campaigns_owner_name_lower (functional unique index)
  8.  Add ix_characters_campaign_name_lower (functional unique index)
  9.  Add ix_npcs_campaign_name_lower (functional unique index)
  10. Create players table
"""

from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SYSTEM_USER_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000000"))


def upgrade() -> None:
    # 1. Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. Insert system user for backfill
    op.execute(
        sa.text(
            "INSERT INTO users (id, username, email, hashed_password, is_active, created_at) "
            "VALUES (:id, 'system', 'system@storyweaver.local', "
            "'$2b$12$disabled.hash.placeholder.not.usable', 0, datetime('now'))"
        ).bindparams(id=_SYSTEM_USER_ID)
    )

    # 3. Add owner_id column as nullable first (for backfill)
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.add_column(
            sa.Column("owner_id", sa.Uuid(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_campaigns_owner_id_users",
            "users",
            ["owner_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    # 4. Backfill: assign all existing campaigns to the system user
    op.execute(
        sa.text("UPDATE campaigns SET owner_id = :system_id").bindparams(
            system_id=_SYSTEM_USER_ID
        )
    )

    # 5. Alter owner_id to NOT NULL (SQLite requires batch mode)
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.alter_column("owner_id", nullable=False)

    # 6. Alter join_code from String(8) to String(6) (batch mode for SQLite)
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.alter_column(
            "join_code",
            type_=sa.String(6),
            existing_type=sa.String(8),
            nullable=False,
        )

    # 7. Functional unique index on campaigns: case-insensitive name per owner
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX ix_campaigns_owner_name_lower "
            "ON campaigns (lower(name), owner_id)"
        )
    )

    # 8. Functional unique index on characters: case-insensitive name per campaign
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX ix_characters_campaign_name_lower "
            "ON characters (lower(name), campaign_id)"
        )
    )

    # 9. Functional unique index on npcs: case-insensitive name per campaign
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX ix_npcs_campaign_name_lower "
            "ON npcs (lower(name), campaign_id)"
        )
    )

    # 10. Create players table
    op.create_table(
        "players",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("player_name", sa.String(100), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX ix_players_campaign_player_name_lower "
            "ON players (lower(player_name), campaign_id)"
        )
    )


def downgrade() -> None:
    # 10. Drop players table and its index
    op.execute(sa.text("DROP INDEX IF EXISTS ix_players_campaign_player_name_lower"))
    op.drop_table("players")

    # 9. Drop npcs functional index
    op.execute(sa.text("DROP INDEX IF EXISTS ix_npcs_campaign_name_lower"))

    # 8. Drop characters functional index
    op.execute(sa.text("DROP INDEX IF EXISTS ix_characters_campaign_name_lower"))

    # 7. Drop campaigns functional index
    op.execute(sa.text("DROP INDEX IF EXISTS ix_campaigns_owner_name_lower"))

    # 6. Revert join_code to String(8)
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.alter_column(
            "join_code",
            type_=sa.String(8),
            existing_type=sa.String(6),
            nullable=False,
        )

    # 5+4+3. Drop owner_id FK and column
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.drop_constraint("fk_campaigns_owner_id_users", type_="foreignkey")
        batch_op.drop_column("owner_id")

    # 2. Remove system user
    op.execute(
        sa.text("DELETE FROM users WHERE id = :id").bindparams(id=_SYSTEM_USER_ID)
    )

    # 1. Drop users table
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
