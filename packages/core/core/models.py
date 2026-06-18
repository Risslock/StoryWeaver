"""SQLAlchemy 2.x ORM models for all StoryWeaver entities."""

from __future__ import annotations

import uuid
from datetime import datetime, date
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Date,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    join_code: Mapped[str] = mapped_column(String(8), nullable=False, unique=True, index=True)
    gm_display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    game_system: Mapped[str] = mapped_column(String(50), nullable=False, default="earthdawn_4e")
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    characters: Mapped[list[Character]] = relationship("Character", back_populates="campaign", cascade="all, delete-orphan")
    npcs: Mapped[list[NPC]] = relationship("NPC", back_populates="campaign", cascade="all, delete-orphan")
    sessions: Mapped[list[Session]] = relationship("Session", back_populates="campaign", cascade="all, delete-orphan")
    session_plans: Mapped[list[SessionPlan]] = relationship("SessionPlan", back_populates="campaign", cascade="all, delete-orphan")


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    player_display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    race: Mapped[str] = mapped_column(String(100), nullable=False)
    discipline: Mapped[str] = mapped_column(String(100), nullable=False)
    circle: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    derived_stats: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    talents: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    skills: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    equipment: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    background: Mapped[str] = mapped_column(Text, nullable=False)
    personality: Mapped[str] = mapped_column(Text, nullable=False)
    goals: Mapped[str | None] = mapped_column(Text, nullable=True)
    relationships: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    physical_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    portrait_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    campaign: Mapped[Campaign] = relationship("Campaign", back_populates="characters")
    digital_twin: Mapped[DigitalTwin | None] = relationship(
        "DigitalTwin",
        primaryjoin="and_(DigitalTwin.entity_type=='character', foreign(DigitalTwin.entity_id)==Character.id)",
        viewonly=True,
        uselist=False,
    )


class NPC(Base):
    __tablename__ = "npcs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    race: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_visible_to_players: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    discipline: Mapped[str | None] = mapped_column(String(100), nullable=True)
    circle: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    derived_stats: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    talents: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    skills: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    background: Mapped[str | None] = mapped_column(Text, nullable=True)
    physical_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    portrait_url: Mapped[str | None] = mapped_column(String, nullable=True)
    gm_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    campaign: Mapped[Campaign] = relationship("Campaign", back_populates="npcs")


class DigitalTwin(Base):
    __tablename__ = "digital_twins"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_twin_entity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "character" | "npc"
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    conversation_history: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    last_active: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("campaign_id", "session_number", name="uq_campaign_session_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    session_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    date_played: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    campaign: Mapped[Campaign] = relationship("Campaign", back_populates="sessions")
    events: Mapped[list[StoryEvent]] = relationship("StoryEvent", back_populates="session", cascade="all, delete-orphan")


class StoryEvent(Base):
    __tablename__ = "story_events"
    __table_args__ = (
        Index("ix_story_events_campaign_session_order", "campaign_id", "session_id", "event_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    participants: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    event_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    session: Mapped[Session | None] = relationship("Session", back_populates="events")


class SessionPlan(Base):
    __tablename__ = "session_plans"
    __table_args__ = (
        UniqueConstraint("campaign_id", "session_id", name="uq_campaign_session_plan"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    annotations: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    campaign: Mapped[Campaign] = relationship("Campaign", back_populates="session_plans")