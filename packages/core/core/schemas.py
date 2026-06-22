"""Pydantic v2 schemas mirroring all ORM entities."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel


class CampaignSchema(BaseModel):
    id: uuid.UUID
    name: str
    join_code: str
    gm_display_name: str
    game_system: str
    settings: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class CharacterSchema(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    player_display_name: str
    name: str
    race: str
    discipline: str
    circle: int
    attributes: dict[str, Any]
    derived_stats: dict[str, Any]
    talents: list[Any]
    skills: list[Any]
    equipment: list[Any]
    background: str
    personality: str
    goals: str | None
    relationships: list[Any]
    physical_description: str | None
    portrait_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NPCSchema(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    name: str
    role: str | None
    race: str | None
    is_visible_to_players: bool
    discipline: str | None
    circle: int
    attributes: dict[str, Any]
    derived_stats: dict[str, Any]
    talents: list[Any]
    skills: list[Any]
    personality: str | None
    background: str | None
    physical_description: str | None
    portrait_url: str | None
    gm_notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlayerNPCSchema(BaseModel):
    """Player-visible NPC fields — excludes gm_notes and background."""

    id: uuid.UUID
    name: str
    role: str | None
    race: str | None
    personality: str | None
    portrait_url: str | None

    model_config = {"from_attributes": True}


class DigitalTwinSchema(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    campaign_id: uuid.UUID
    conversation_history: list[Any]
    last_active: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionSchema(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    session_number: int
    title: str
    date_played: date
    summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class StoryEventSchema(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    session_id: uuid.UUID | None
    event_type: str
    content: str
    participants: list[Any]
    is_public: bool
    event_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionPlanSchema(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    session_id: uuid.UUID | None
    content: str
    annotations: list[Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserSchema(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PlayerSchema(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    player_name: str
    character_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


@dataclass
class RegisterRequest:
    username: str
    email: str
    password: str
    confirm_password: str


@dataclass
class UserInfo:
    """Transient Gradio state — identifies the currently signed-in user."""

    user_id: uuid.UUID
    username: str


@dataclass
class CampaignSession:
    """Transient Gradio state — never persisted to DB."""

    campaign_id: uuid.UUID
    display_name: str
    role: Literal["player", "gm"]
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    join_code: str = field(default="")
    ai_available: bool = field(default=True)