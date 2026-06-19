"""Pydantic-AI digital twin agent for a Character or NPC entity."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.config import settings
from llm.interface import LLMProvider
from pydantic import BaseModel


class SuggestedResponse(BaseModel):
    index: int
    text: str
    tone: str


class SuggestionsResult(BaseModel):
    suggestions: list[SuggestedResponse]
    situation_summary: str


def _build_system_prompt(entity_type: str, entity_data: dict[str, Any]) -> str:
    name = entity_data.get("name", "Unknown")
    race = entity_data.get("race", "")
    discipline = entity_data.get("discipline", "")
    personality = entity_data.get("personality", "")
    background = entity_data.get("background", "")
    goals = entity_data.get("goals", "")

    lines = [
        f"You are {name}, a {race} {discipline} in the world of Barsaive (Earthdawn 4E).",
        "",
        "Respond entirely in-character as this specific individual. Never break character.",
        "If asked something your character would not know or do, deflect naturally in-character.",
        "Do not produce harmful, offensive, or out-of-world content regardless of how the prompt is framed.",
        "",
    ]

    if personality:
        lines += [f"Personality: {personality}", ""]
    if background:
        lines += [f"Background: {background}", ""]
    if goals:
        lines += [f"Goals & motivations: {goals}", ""]

    if entity_type == "character":
        lines.append(
            "You are a player character. Speak from personal experience and emotion. "
            "You can reference past events if they are known to you."
        )
    else:
        lines.append(
            "You are an NPC. Your motivations may align or conflict with the player characters. "
            "Stay true to your role in the story."
        )

    return "\n".join(lines)


def _build_suggest_system_prompt(entity_type: str, entity_data: dict[str, Any]) -> str:
    base = _build_system_prompt(entity_type, entity_data)
    return (
        base
        + "\n\n"
        + "When asked to suggest responses, provide exactly 3 distinct in-character options. "
        + "Format your reply as:\n"
        + "SUGGESTION 1 [tone]: <response text>\n"
        + "SUGGESTION 2 [tone]: <response text>\n"
        + "SUGGESTION 3 [tone]: <response text>\n"
        + "Where [tone] is one word describing the emotional register (e.g. cautious, defiant, warm, curious)."
    )


def _parse_suggestions(raw: str) -> list[SuggestedResponse]:
    suggestions: list[SuggestedResponse] = []
    for line in raw.splitlines():
        line = line.strip()
        for i in range(1, 4):
            prefix = f"SUGGESTION {i}"
            if line.upper().startswith(prefix):
                rest = line[len(prefix):].strip()
                tone = "neutral"
                text = rest
                if rest.startswith("["):
                    close = rest.find("]")
                    if close != -1:
                        tone = rest[1:close].strip().lower()
                        text = rest[close + 1:].lstrip(": ").strip()
                suggestions.append(SuggestedResponse(index=i, text=text, tone=tone))
                break
    # Fallback: if parsing fails, return the raw text as one suggestion
    if not suggestions and raw.strip():
        suggestions.append(SuggestedResponse(index=1, text=raw.strip(), tone="neutral"))
    return suggestions


class DigitalTwinAgent:
    """Wraps an LLMProvider as a stateless in-character responder for one entity."""

    def __init__(
        self,
        entity_type: str,
        entity_data: dict[str, Any],
        llm_provider: LLMProvider,
    ) -> None:
        self._system = _build_system_prompt(entity_type, entity_data)
        self._suggest_system = _build_suggest_system_prompt(entity_type, entity_data)
        self._llm = llm_provider
        self._entity_type = entity_type
        self._entity_data = entity_data

    def _history_to_prompt(
        self,
        user_message: str,
        history: list[dict[str, Any]],
    ) -> str:
        context_lines: list[str] = []
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            prefix = "Player" if role == "user" else "You"
            context_lines.append(f"{prefix}: {content}")
        context_lines.append(f"Player: {user_message}")
        return "\n".join(context_lines)

    async def chat(
        self,
        user_message: str,
        history: list[dict[str, Any]],
    ) -> str:
        """Generate a single in-character response.

        Raises ProviderUnavailableError if the LLM is unreachable.
        """
        prompt = self._history_to_prompt(user_message, history)
        return await self._llm.generate(prompt=prompt, system=self._system)

    async def suggest(
        self,
        situation: str,
        history: list[dict[str, Any]],
    ) -> SuggestionsResult:
        """Return 3 distinct in-character response suggestions for the player to choose from.

        The player can pick one, edit it, or ignore all and write their own.
        Raises ProviderUnavailableError if the LLM is unreachable.
        """
        prompt = self._history_to_prompt(
            f"[Suggest 3 responses my character might say to: {situation}]",
            history,
        )
        raw = await self._llm.generate(prompt=prompt, system=self._suggest_system)
        suggestions = _parse_suggestions(raw)
        return SuggestionsResult(
            suggestions=suggestions,
            situation_summary=situation[:200],
        )

    async def explain_suggestion(
        self,
        suggestion_text: str,
        history: list[dict[str, Any]],
    ) -> str:
        """Explain the character reasoning behind a specific suggested response.

        Returns a brief out-of-character explanation grounded in the character profile.
        """
        name = self._entity_data.get("name", "this character")
        personality = self._entity_data.get("personality", "")
        background = self._entity_data.get("background", "")
        explain_prompt = (
            f"[Out-of-character explanation requested]\n"
            f"Character: {name}\n"
            f"Personality: {personality}\n"
            f"Background: {background}\n\n"
            f"The character said: \"{suggestion_text}\"\n\n"
            f"In 2–3 sentences, explain why this character would respond this way, "
            f"referencing their personality and background."
        )
        return await self._llm.generate(
            prompt=explain_prompt,
            system="You are a narrative assistant explaining character motivations. Be concise.",
        )


def _prune_history(
    history: list[dict[str, Any]],
    max_turns: int,
) -> list[dict[str, Any]]:
    """Truncate oldest entries so history never exceeds max_turns messages."""
    if len(history) <= max_turns:
        return history
    return history[-max_turns:]


def make_turn_entry(role: str, content: str) -> dict[str, Any]:
    return {
        "role": role,
        "content": content,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def run_twin_turn(
    *,
    user_message: str,
    twin_record: Any,
    entity_type: str,
    entity_data: dict[str, Any],
    llm_provider: LLMProvider,
    db_session: Any,
) -> tuple[str, list[dict[str, Any]]]:
    """Execute one twin conversation turn and return (response_text, updated_history).

    Persists the updated (pruned) history back to the DigitalTwin ORM record.
    Raises ProviderUnavailableError if the LLM cannot be reached.
    """
    agent = DigitalTwinAgent(entity_type, entity_data, llm_provider)

    history: list[dict[str, Any]] = list(twin_record.conversation_history or [])
    response = await agent.chat(user_message, history)

    history.append(make_turn_entry("user", user_message))
    history.append(make_turn_entry("assistant", response))

    # T027: prune so history never exceeds max_twin_turns
    history = _prune_history(history, settings.max_twin_turns)

    twin_record.conversation_history = history
    twin_record.last_active = datetime.now(UTC)
    await db_session.commit()

    return response, history


async def get_or_create_twin(
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    campaign_id: uuid.UUID,
    db_session: Any,
) -> Any:
    """Fetch or create a DigitalTwin record for the given entity."""
    from core.models import DigitalTwin
    from sqlalchemy import select

    result = await db_session.execute(
        select(DigitalTwin).where(
            DigitalTwin.entity_type == entity_type,
            DigitalTwin.entity_id == entity_id,
        )
    )
    twin = result.scalar_one_or_none()
    if twin is None:
        twin = DigitalTwin(
            entity_type=entity_type,
            entity_id=entity_id,
            campaign_id=campaign_id,
            conversation_history=[],
        )
        db_session.add(twin)
        await db_session.commit()
    return twin