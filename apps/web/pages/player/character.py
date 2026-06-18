"""Player character sheet view and creation form."""

from __future__ import annotations

import uuid
from typing import Any

import gradio as gr
from sqlalchemy import select

from core.config import settings
from core.models import Character
from core.schemas import CampaignSession, CharacterSchema
from rules_earthdawn.character_builder import (
    CREATION_STEPS,
    default_creation_state,
    discipline_names,
    race_names,
)
from rules_earthdawn.validator import validate_character
from storage.sqlite.adapter import SQLiteBackend

_backend = SQLiteBackend(settings.database_url)

_EARTHDAWN_RACES = race_names()
_EARTHDAWN_DISCIPLINES = discipline_names()


async def _load_characters(campaign_id: uuid.UUID, player_name: str) -> list[Character]:
    async with await _backend.get_session() as session:
        result = await session.execute(
            select(Character).where(
                Character.campaign_id == campaign_id,
                Character.player_display_name == player_name,
            )
        )
        return list(result.scalars().all())


async def _save_character(campaign_id: uuid.UUID, player_name: str, data: dict[str, Any]) -> Character:
    async with await _backend.get_session() as session:
        char = Character(
            id=uuid.uuid4(),
            campaign_id=campaign_id,
            player_display_name=player_name,
            **data,
        )
        session.add(char)
        await session.commit()
        await session.refresh(char)
        return char


async def _update_character(char_id: uuid.UUID, updates: dict[str, Any]) -> Character | None:
    async with await _backend.get_session() as session:
        result = await session.execute(select(Character).where(Character.id == char_id))
        char = result.scalar_one_or_none()
        if char is None:
            return None
        for k, v in updates.items():
            setattr(char, k, v)
        await session.commit()
        await session.refresh(char)
        return char


def _render_character_sheet(char: Character) -> str:
    schema = CharacterSchema.model_validate(char)
    tier = ""
    try:
        from rules_earthdawn.character_builder import tier_for_circle
        tier = f" ({tier_for_circle(schema.circle)})"
    except Exception:
        pass

    attrs = schema.attributes
    attr_line = " | ".join(
        f"**{k.upper()}** {v}" for k, v in attrs.items()
    ) if attrs else "—"

    talents_md = "\n".join(
        f"- {t.get('name', '?')} (Circle {t.get('circle', '?')}, Rank {t.get('rank', '?')})"
        for t in schema.talents
    ) or "None"

    skills_md = "\n".join(
        f"- {s.get('name', '?')} (Rank {s.get('rank', '?')})"
        for s in schema.skills
    ) or "None"

    equipment_md = "\n".join(
        f"- {e.get('name', '?')} [{e.get('type', '?')}]"
        for e in schema.equipment
    ) or "None"

    relationships_md = "\n".join(
        f"- **{r.get('name', '?')}** — {r.get('nature', '?')}"
        for r in schema.relationships
    ) or "None"

    portrait_line = (
        f"![Portrait]({schema.portrait_url})" if schema.portrait_url
        else "*No portrait generated yet.*"
    )

    return f"""## {schema.name}
*{schema.race} {schema.discipline} — Circle {schema.circle}{tier}*

{portrait_line}

---

### Attributes
{attr_line}

---

### Background
{schema.background or "—"}

### Personality
{schema.personality or "—"}

### Goals
{schema.goals or "—"}

### Physical Description
{schema.physical_description or "—"}

---

### Talents
{talents_md}

### Skills
{skills_md}

### Equipment
{equipment_md}

### Relationships
{relationships_md}
"""


def build_character_page(session_state: gr.State) -> None:
    """Build the player character tab UI. Must be called inside a gr.Blocks context."""

    with gr.Tab("Characters"):
        gr.Markdown("## Your Characters")

        with gr.Row():
            char_selector = gr.Dropdown(
                label="Select Character",
                choices=[],
                value=None,
                interactive=True,
                scale=3,
            )
            refresh_btn = gr.Button("↻ Refresh", scale=1)

        character_sheet = gr.Markdown("*Select a character or create a new one below.*")

        gr.Markdown("---")
        gr.Markdown("### Create New Character")

        with gr.Group():
            with gr.Row():
                char_name = gr.Textbox(label="Character Name", placeholder="Brekk Stonefist")
                char_race = gr.Dropdown(
                    label="Race",
                    choices=_EARTHDAWN_RACES,
                    value=_EARTHDAWN_RACES[2] if len(_EARTHDAWN_RACES) > 2 else None,
                )
            with gr.Row():
                char_discipline = gr.Dropdown(
                    label="Discipline",
                    choices=_EARTHDAWN_DISCIPLINES,
                    value=_EARTHDAWN_DISCIPLINES[12] if len(_EARTHDAWN_DISCIPLINES) > 12 else None,
                )
                char_circle = gr.Slider(label="Circle", minimum=1, maximum=15, step=1, value=1)

        gr.Markdown("#### Attributes (step values)")
        with gr.Row():
            attr_dex = gr.Number(label="DEX", value=10, precision=0, minimum=1)
            attr_str = gr.Number(label="STR", value=10, precision=0, minimum=1)
            attr_tou = gr.Number(label="TOU", value=10, precision=0, minimum=1)
            attr_per = gr.Number(label="PER", value=10, precision=0, minimum=1)
            attr_wil = gr.Number(label="WIL", value=10, precision=0, minimum=1)
            attr_cha = gr.Number(label="CHA", value=10, precision=0, minimum=1)

        with gr.Group():
            char_background = gr.Textbox(
                label="Background *",
                placeholder="Where did your character come from? What shaped them?",
                lines=3,
            )
            char_personality = gr.Textbox(
                label="Personality *",
                placeholder="How do they think, speak, and act?",
                lines=2,
            )
            char_goals = gr.Textbox(
                label="Goals & Motivations",
                placeholder="What drives them forward?",
                lines=2,
            )
            char_physical = gr.Textbox(
                label="Physical Description",
                placeholder="Describe their appearance — this grounds the digital twin and portrait generation.",
                lines=2,
            )

        with gr.Accordion("Talents, Skills & Equipment", open=False):
            gr.Markdown(
                "Add talents, skills, and equipment as JSON lists. "
                "Example talent: `{\"name\": \"Melee Weapons\", \"circle\": 1, \"rank\": 4}`"
            )
            talents_json = gr.Code(
                label="Talents (JSON array)",
                language="json",
                value="[]",
            )
            skills_json = gr.Code(
                label="Skills (JSON array)",
                language="json",
                value="[]",
            )
            equipment_json = gr.Code(
                label="Equipment (JSON array)",
                language="json",
                value="[]",
            )

        with gr.Row():
            save_btn = gr.Button("Save Character", variant="primary")
            save_status = gr.Markdown("")

        portrait_btn = gr.Button("Generate Portrait (coming in Phase 6)", interactive=False)

        # ── Event handlers ────────────────────────────────────────────────

        async def load_char_list(state: CampaignSession | None) -> dict[str, Any]:
            if state is None:
                return gr.update(choices=[], value=None)
            chars = await _load_characters(state.campaign_id, state.display_name)
            choices = [(c.name, str(c.id)) for c in chars]
            return gr.update(choices=choices, value=choices[0][1] if choices else None)

        async def on_select_char(char_id: str | None) -> str:
            if not char_id:
                return "*No character selected.*"
            async with await _backend.get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == uuid.UUID(char_id))
                )
                char = result.scalar_one_or_none()
            if char is None:
                return "*Character not found.*"
            return _render_character_sheet(char)

        async def on_save(
            state: CampaignSession | None,
            name: str,
            race: str,
            discipline: str,
            circle: int,
            dex: float, str_: float, tou: float, per: float, wil: float, cha: float,
            background: str,
            personality: str,
            goals: str,
            physical: str,
            talents_raw: str,
            skills_raw: str,
            equipment_raw: str,
        ) -> tuple[str, dict[str, Any]]:
            if state is None:
                return "Error: not in a campaign session.", gr.update()

            import json as _json

            data: dict[str, Any] = {
                "name": name.strip(),
                "race": race,
                "discipline": discipline,
                "circle": int(circle),
                "attributes": {
                    "dex": int(dex), "str": int(str_), "tou": int(tou),
                    "per": int(per), "wil": int(wil), "cha": int(cha),
                },
                "derived_stats": {},
                "talents": [],
                "skills": [],
                "equipment": [],
                "relationships": [],
                "background": background.strip(),
                "personality": personality.strip(),
                "goals": goals.strip(),
                "physical_description": physical.strip(),
            }

            try:
                data["talents"] = _json.loads(talents_raw or "[]")
                data["skills"] = _json.loads(skills_raw or "[]")
                data["equipment"] = _json.loads(equipment_raw or "[]")
            except _json.JSONDecodeError as exc:
                return f"JSON parse error: {exc}", gr.update()

            from rules_earthdawn.character_builder import _compute_derived, CreationState
            cs = CreationState(**{
                k: data[k] for k in (
                    "name", "race", "discipline", "circle", "attributes",
                    "derived_stats", "talents", "skills", "equipment",
                    "background", "personality", "goals", "relationships",
                    "physical_description",
                )
            })
            _compute_derived(cs)
            data["derived_stats"] = cs.derived_stats

            from rules_earthdawn.validator import validate_character
            result = validate_character(data)
            if not result.valid:
                return "Validation errors:\n" + "\n".join(f"- {e}" for e in result.errors), gr.update()

            await _save_character(state.campaign_id, state.display_name, data)

            chars = await _load_characters(state.campaign_id, state.display_name)
            choices = [(c.name, str(c.id)) for c in chars]
            return (
                f"✓ Character **{data['name']}** saved!",
                gr.update(choices=choices, value=choices[-1][1] if choices else None),
            )

        session_state.change(load_char_list, inputs=[session_state], outputs=[char_selector])
        refresh_btn.click(load_char_list, inputs=[session_state], outputs=[char_selector])
        char_selector.change(on_select_char, inputs=[char_selector], outputs=[character_sheet])
        save_btn.click(
            on_save,
            inputs=[
                session_state,
                char_name, char_race, char_discipline, char_circle,
                attr_dex, attr_str, attr_tou, attr_per, attr_wil, attr_cha,
                char_background, char_personality, char_goals, char_physical,
                talents_json, skills_json, equipment_json,
            ],
            outputs=[save_status, char_selector],
        )