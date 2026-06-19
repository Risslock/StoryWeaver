"""GM characters overview — read-only view of all campaign characters."""

from __future__ import annotations

import uuid
from typing import Any

import gradio as gr
from core.config import settings
from core.models import Character
from core.schemas import CampaignSession, CharacterSchema
from sqlalchemy import select
from storage.sqlite.adapter import SQLiteBackend

_backend = SQLiteBackend(settings.database_url)


async def _load_all_characters(campaign_id: uuid.UUID) -> list[Character]:
    async with await _backend.get_session() as session:
        result = await session.execute(
            select(Character).where(Character.campaign_id == campaign_id)
        )
        return list(result.scalars().all())


def _render_character_detail(char: Character) -> str:
    schema = CharacterSchema.model_validate(char)
    portrait_line = (
        f"![Portrait]({schema.portrait_url})" if schema.portrait_url
        else "*No portrait generated yet.*"
    )
    attrs = schema.attributes
    attr_line = (
        " | ".join(f"**{k.upper()}** {v}" for k, v in attrs.items()) if attrs else "—"
    )
    return f"""## {schema.name}
*{schema.race} {schema.discipline} — Circle {schema.circle}*
**Player**: {schema.player_display_name}

{portrait_line}

---

### Attributes
{attr_line}

### Background
{schema.background or "—"}

### Personality
{schema.personality or "—"}

### Goals
{schema.goals or "—"}
"""


def build_characters_page(session_state: gr.State) -> None:
    """Build the GM characters overview tab. Must be called inside a gr.Blocks context."""  # noqa: E501

    with gr.Tab("Characters"):
        gr.Markdown("## Campaign Characters")
        gr.Markdown("*Read-only overview of all player characters in this campaign.*")

        with gr.Row():
            refresh_btn = gr.Button("↻ Refresh")

        characters_table = gr.Dataframe(
            headers=["Name", "Race", "Discipline", "Circle", "Player"],
            datatype=["str", "str", "str", "number", "str"],
            label="All Characters",
            interactive=False,
            col_count=(5, "fixed"),
        )

        char_detail = gr.Markdown("*Select a row to view character details.*")

        # Internal state: list of character IDs matching table rows
        char_ids_state: gr.State = gr.State(value=[])

        async def load_characters(
            state: CampaignSession | None,
        ) -> tuple[list[list[Any]], list[str]]:
            if state is None:
                return [], []
            chars = await _load_all_characters(state.campaign_id)
            rows = [
                [c.name, c.race, c.discipline, c.circle, c.player_display_name]
                for c in chars
            ]
            ids = [str(c.id) for c in chars]
            return rows, ids

        async def on_select_row(
            evt: gr.SelectData,
            ids: list[str],
        ) -> str:
            if not ids or evt.index[0] >= len(ids):
                return "*No character selected.*"
            char_id = uuid.UUID(ids[evt.index[0]])
            async with await _backend.get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == char_id)
                )
                char = result.scalar_one_or_none()
            if char is None:
                return "*Character not found.*"
            return _render_character_detail(char)

        async def on_refresh(
            state: CampaignSession | None,
        ) -> tuple[dict[str, Any], list[str]]:
            rows, ids = await load_characters(state)
            return gr.update(value=rows), ids

        session_state.change(
            on_refresh,
            inputs=[session_state],
            outputs=[characters_table, char_ids_state],
        )
        refresh_btn.click(
            on_refresh,
            inputs=[session_state],
            outputs=[characters_table, char_ids_state],
        )
        characters_table.select(
            on_select_row,
            inputs=[char_ids_state],
            outputs=[char_detail],
        )