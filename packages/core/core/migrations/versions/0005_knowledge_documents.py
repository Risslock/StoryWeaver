"""Add knowledge_documents table

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("access_level_default", sa.String(16), nullable=True),
        sa.Column("ingestion_status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "campaign_id", "title", name="uq_knowledge_doc_title"),
    )
    op.create_index("ix_knowledge_documents_campaign_id", "knowledge_documents", ["campaign_id"])
    op.create_index("ix_knowledge_documents_ingestion_status", "knowledge_documents", ["ingestion_status"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_ingestion_status", "knowledge_documents")
    op.drop_index("ix_knowledge_documents_campaign_id", "knowledge_documents")
    op.drop_table("knowledge_documents")
