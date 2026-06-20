"""Player character sheet view and creation form."""

from __future__ import annotations

import uuid
from typing import Any

import gradio as gr
from components.image_display import build_portrait_display
from core.models import Character, Player
from core.schemas import CampaignSession, CharacterSchema
from rules_earthdawn.character_builder import (
    discipline_names,
    race_names,
)
from services.db import get_backend
from sqlalchemy import func, select

_EARTHDAWN_RACES = race_names()
_EARTHDAWN_DISCIPLINES = discipline_names()


async def _load_characters(
    campaign_id: uuid.UUID, user_id: uuid.UUID
) -> list[Character]:
    """Load characters for the player identified by (campaign_id, user_id)."""
    backend = get_backend()
    async with await backend.get_session() as session:
        player_result = await session.execute(
            select(Player).where(
                Player.campaign_id == campaign_id,
                Player.user_id == user_id,
            )
        )
        player = player_result.scalar_one_or_none()
        if player is None:
            return []
        result = await session.execute(
            select(Character).where(
                Character.campaign_id == campaign_id,
                Character.player_display_name == player.player_name,
            )
        )
        return list(result.scalars().all())


async def _save_character(
    campaign_id: uuid.UUID, player_name: str, data: dict[str, Any]
) -> Character:
    backend = get_backend()
    async with await backend.get_session() as session:
        result = await session.execute(
            select(Character).where(
                Character.campaign_id == campaign_id,
                func.lower(Character.name) == data["name"].lower(),
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            for k, v in data.items():
                if k not in ("id", "created_at", "campaign_id"):
                    setattr(existing, k, v)
            existing.player_display_name = player_name
            await session.commit()
            await session.refresh(existing)
            return existing
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


async def _update_character(
    char_id: uuid.UUID, updates: dict[str, Any]
) -> Character | None:
    backend = get_backend()
    async with await backend.get_session() as session:
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
    attr_line = (
        " | ".join(f"**{k.upper()}** {v}" for k, v in attrs.items()) if attrs else "—"
    )

    talents_md = (
        "\n".join(
            f"- {t.get('name', '?')}"
            f" (Circle {t.get('circle', '?')}, Rank {t.get('rank', '?')})"
            for t in schema.talents
        )
        or "None"
    )

    skills_md = (
        "\n".join(
            f"- {s.get('name', '?')} (Rank {s.get('rank', '?')})" for s in schema.skills
        )
        or "None"
    )

    equipment_md = (
        "\n".join(
            f"- {e.get('name', '?')} [{e.get('type', '?')}]" for e in schema.equipment
        )
        or "None"
    )

    relationships_md = (
        "\n".join(
            f"- **{r.get('name', '?')}** — {r.get('nature', '?')}"
            for r in schema.relationships
        )
        or "None"
    )

    return f"""## {schema.name}
*{schema.race} {schema.discipline} — Circle {schema.circle}{tier}*

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

        portrait_image = build_portrait_display("Character Portrait")
        character_sheet = gr.Markdown("*Select a character or create a new one below.*")

        gr.Markdown("---")
        gr.Markdown("### Create New Character")

        with gr.Group():
            with gr.Row():
                char_name = gr.Textbox(
                    label="Character Name", placeholder="Brekk Stonefist"
                )
                char_race = gr.Dropdown(
                    label="Race",
                    choices=_EARTHDAWN_RACES,
                    value=_EARTHDAWN_RACES[2] if len(_EARTHDAWN_RACES) > 2 else None,
                )
            with gr.Row():
                char_discipline = gr.Dropdown(
                    label="Discipline",
                    choices=_EARTHDAWN_DISCIPLINES,
                    value=(
                        _EARTHDAWN_DISCIPLINES[12]
                        if len(_EARTHDAWN_DISCIPLINES) > 12
                        else None
                    ),
                )
                char_circle = gr.Slider(
                    label="Circle", minimum=1, maximum=15, step=1, value=1
                )

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
                placeholder=(
                    "Describe their appearance"
                    " — this grounds the digital twin and portrait generation."
                ),
                lines=2,
            )

        with gr.Accordion("Talents, Skills & Equipment", open=False):
            gr.Markdown(
                "Add talents, skills, and equipment as JSON lists. "
                "Example talent: "
                '`{"name": "Melee Weapons", "circle": 1, "rank": 4}`'
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

        with gr.Row():
            portrait_btn = gr.Button(
                "Generate Portrait", variant="secondary", interactive=False
            )
            portrait_status = gr.Markdown("")

        selected_char_id: gr.State = gr.State(value=None)

        # ── Event handlers ────────────────────────────────────────────────

        async def load_char_list(state: CampaignSession | None) -> dict[str, Any]:
            if state is None:
                return gr.update(choices=[], value=None)
            chars = await _load_characters(state.campaign_id, state.user_id)
            choices = [(c.name, str(c.id)) for c in chars]
            return gr.update(choices=choices, value=choices[0][1] if choices else None)

        async def on_select_char(char_id: str | None) -> tuple[str | None, str, Any]:
            if not char_id:
                return None, "*No character selected.*", char_id
            backend = get_backend()
            async with await backend.get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == uuid.UUID(char_id))
                )
                char = result.scalar_one_or_none()
            if char is None:
                return None, "*Character not found.*", char_id
            return char.portrait_url or None, _render_character_sheet(char), char_id

        async def on_generate_portrait(
            state: CampaignSession | None,
            char_id_val: str | None,
        ) -> tuple[str | None, str]:
            if state is None or not char_id_val:
                return None, "Select a character first."
            if not state.ai_available:
                return None, "AI features unavailable in degraded mode."

            backend = get_backend()
            async with await backend.get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == uuid.UUID(char_id_val))
                )
                char = result.scalar_one_or_none()
                if char is None:
                    return None, "Character not found."

            if not (char.physical_description or "").strip():
                return None, "Add a physical description to your character first."

            from imagegen.factory import get_image_provider
            from imagegen.interface import (
                PORTRAIT_NEGATIVE_PROMPT,
                PORTRAIT_PROMPT_PREFIX,
                ImageGenRequest,
            )

            prompt = (
                f"{PORTRAIT_PROMPT_PREFIX}, "
                f"{char.name}, {char.race} {char.discipline}, "
                f"{char.physical_description}"
            )
            request = ImageGenRequest(
                prompt=prompt,
                negative_prompt=PORTRAIT_NEGATIVE_PROMPT,
                entity_id=char.id,
            )

            provider = get_image_provider()
            response = await provider.generate(request)

            if response.error:
                return None, f"Portrait generation failed: {response.error}"

            await _update_character(char.id, {"portrait_url": response.image_url})
            return response.image_url, "Portrait generated!"

        async def on_save(
            state: CampaignSession | None,
            name: str,
            race: str,
            discipline: str,
            circle: int,
            dex: float,
            str_: float,
            tou: float,
            per: float,
            wil: float,
            cha: float,
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
                    "dex": int(dex),
                    "str": int(str_),
                    "tou": int(tou),
                    "per": int(per),
                    "wil": int(wil),
                    "cha": int(cha),
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

            from rules_earthdawn.character_builder import (
                CreationState,
                _compute_derived,
            )

            cs = CreationState(
                **{
                    k: data[k]
                    for k in (
                        "name",
                        "race",
                        "discipline",
                        "circle",
                        "attributes",
                        "derived_stats",
                        "talents",
                        "skills",
                        "equipment",
                        "background",
                        "personality",
                        "goals",
                        "relationships",
                        "physical_description",
                    )
                }
            )
            _compute_derived(cs)
            data["derived_stats"] = cs.derived_stats

            from rules_earthdawn.validator import validate_character

            result = validate_character(data)
            if not result.valid:
                msg = "Validation errors:\n" + "\n".join(
                    f"- {e}" for e in result.errors
                )
                return msg, gr.update()

            await _save_character(state.campaign_id, state.display_name, data)

            chars = await _load_characters(state.campaign_id, state.user_id)
            choices = [(c.name, str(c.id)) for c in chars]
            return (
                f"✓ Character **{data['name']}** saved!",
                gr.update(choices=choices, value=choices[-1][1] if choices else None),
            )

        def _update_portrait_btn(state: CampaignSession | None) -> dict[str, Any]:
            ai_ok = state.ai_available if state is not None else False
            return gr.update(interactive=ai_ok)

        session_state.change(
            load_char_list, inputs=[session_state], outputs=[char_selector]
        )
        session_state.change(
            _update_portrait_btn, inputs=[session_state], outputs=[portrait_btn]
        )
        refresh_btn.click(
            load_char_list, inputs=[session_state], outputs=[char_selector]
        )
        char_selector.change(
            on_select_char,
            inputs=[char_selector],
            outputs=[portrait_image, character_sheet, selected_char_id],
        )
        save_btn.click(
            on_save,
            inputs=[
                session_state,
                char_name,
                char_race,
                char_discipline,
                char_circle,
                attr_dex,
                attr_str,
                attr_tou,
                attr_per,
                attr_wil,
                attr_cha,
                char_background,
                char_personality,
                char_goals,
                char_physical,
                talents_json,
                skills_json,
                equipment_json,
            ],
            outputs=[save_status, char_selector],
        )
        portrait_btn.click(
            on_generate_portrait,
            inputs=[session_state, selected_char_id],
            outputs=[portrait_image, portrait_status],
        )
