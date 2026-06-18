"""Player role agent — character management tools with access control."""

from __future__ import annotations

import uuid
from typing import Any

from core.errors import AccessDeniedError, EntityNotFoundError, ValidationError
from core.models import Character
from core.schemas import CharacterSchema
from pydantic import BaseModel
from sqlalchemy import select


class GetCharacterInput(BaseModel):
    character_id: uuid.UUID


class UpdateCharacterInput(BaseModel):
    character_id: uuid.UUID
    field: str
    value: Any


class UpdateCharacterOutput(BaseModel):
    success: bool
    updated_field: str
    updated_value: Any


class ListCharactersInput(BaseModel):
    campaign_id: uuid.UUID


class CharacterSummary(BaseModel):
    id: uuid.UUID
    name: str
    race: str
    discipline: str
    circle: int
    has_portrait: bool


class ListCharactersOutput(BaseModel):
    characters: list[CharacterSummary]


# portrait_url is excluded — image generation is a separate flow
_UPDATABLE_FIELDS = frozenset({
    "name", "circle", "attributes", "derived_stats",
    "talents", "skills", "equipment",
    "background", "personality", "goals",
    "relationships", "physical_description",
})


def build_player_agent_tools(
    player_display_name: str,
    campaign_id: uuid.UUID,
    db_session: Any,
) -> dict[str, Any]:
    """Return async tool callables for the Player role.

    All tools enforce that the player can only access their own characters.
    """

    async def get_character_sheet(inp: GetCharacterInput) -> CharacterSchema:
        result = await db_session.execute(
            select(Character).where(Character.id == inp.character_id)
        )
        char = result.scalar_one_or_none()
        if char is None:
            raise EntityNotFoundError(f"Character {inp.character_id} not found.")
        if char.player_display_name != player_display_name:
            raise AccessDeniedError(
                f"Character {inp.character_id} does not belong to {player_display_name!r}."
            )
        return CharacterSchema.model_validate(char)

    async def update_character_field(inp: UpdateCharacterInput) -> UpdateCharacterOutput:
        if inp.field not in _UPDATABLE_FIELDS:
            raise ValidationError(
                f"Field {inp.field!r} is not updatable via this tool."
            )
        result = await db_session.execute(
            select(Character).where(Character.id == inp.character_id)
        )
        char = result.scalar_one_or_none()
        if char is None:
            raise EntityNotFoundError(f"Character {inp.character_id} not found.")
        if char.player_display_name != player_display_name:
            raise AccessDeniedError(
                f"Character {inp.character_id} does not belong to {player_display_name!r}."
            )
        setattr(char, inp.field, inp.value)
        await db_session.commit()
        return UpdateCharacterOutput(
            success=True,
            updated_field=inp.field,
            updated_value=inp.value,
        )

    async def list_own_characters(inp: ListCharactersInput) -> ListCharactersOutput:
        result = await db_session.execute(
            select(Character).where(
                Character.campaign_id == inp.campaign_id,
                Character.player_display_name == player_display_name,
            )
        )
        chars = list(result.scalars().all())
        return ListCharactersOutput(
            characters=[
                CharacterSummary(
                    id=c.id,
                    name=c.name,
                    race=c.race,
                    discipline=c.discipline,
                    circle=c.circle,
                    has_portrait=c.portrait_url is not None,
                )
                for c in chars
            ]
        )

    return {
        "get_character_sheet": get_character_sheet,
        "update_character_field": update_character_field,
        "list_own_characters": list_own_characters,
    }