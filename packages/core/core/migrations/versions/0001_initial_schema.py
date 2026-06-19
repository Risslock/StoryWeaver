"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("join_code", sa.String(8), nullable=False),
        sa.Column("gm_display_name", sa.String(100), nullable=False),
        sa.Column("game_system", sa.String(50), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("join_code"),
    )
    op.create_index("ix_campaigns_join_code", "campaigns", ["join_code"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("session_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("date_played", sa.Date(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id", "session_number", name="uq_campaign_session_number"
        ),
    )

    op.create_table(
        "characters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("player_display_name", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("race", sa.String(100), nullable=False),
        sa.Column("discipline", sa.String(100), nullable=False),
        sa.Column("circle", sa.Integer(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("derived_stats", sa.JSON(), nullable=False),
        sa.Column("talents", sa.JSON(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("equipment", sa.JSON(), nullable=False),
        sa.Column("background", sa.Text(), nullable=False),
        sa.Column("personality", sa.Text(), nullable=False),
        sa.Column("goals", sa.Text(), nullable=True),
        sa.Column("relationships", sa.JSON(), nullable=False),
        sa.Column("physical_description", sa.Text(), nullable=True),
        sa.Column("portrait_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "npcs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("race", sa.String(100), nullable=True),
        sa.Column("is_visible_to_players", sa.Boolean(), nullable=False),
        sa.Column("discipline", sa.String(100), nullable=True),
        sa.Column("circle", sa.Integer(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("derived_stats", sa.JSON(), nullable=False),
        sa.Column("talents", sa.JSON(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("personality", sa.Text(), nullable=True),
        sa.Column("background", sa.Text(), nullable=True),
        sa.Column("physical_description", sa.Text(), nullable=True),
        sa.Column("portrait_url", sa.String(), nullable=True),
        sa.Column("gm_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "digital_twins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_history", sa.JSON(), nullable=False),
        sa.Column("last_active", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_type", "entity_id", name="uq_twin_entity"),
    )

    op.create_table(
        "story_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("participants", sa.JSON(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("event_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_story_events_campaign_session_order",
        "story_events",
        ["campaign_id", "session_id", "event_order"],
    )

    op.create_table(
        "session_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("annotations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id", "session_id", name="uq_campaign_session_plan"
        ),
    )


def downgrade() -> None:
    op.drop_table("session_plans")
    op.drop_index("ix_story_events_campaign_session_order", table_name="story_events")
    op.drop_table("story_events")
    op.drop_table("digital_twins")
    op.drop_table("npcs")
    op.drop_table("characters")
    op.drop_table("sessions")
    op.drop_index("ix_campaigns_join_code", table_name="campaigns")
    op.drop_table("campaigns")
