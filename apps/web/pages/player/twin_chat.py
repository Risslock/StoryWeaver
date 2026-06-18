"""Player digital twin chat tab."""

from __future__ import annotations

import uuid
from typing import Any

import gradio as gr
from sqlalchemy import select

from core.config import settings
from core.errors import ProviderUnavailableError
from core.models import Character
from core.schemas import CampaignSession
from storage.sqlite.adapter import SQLiteBackend

_backend = SQLiteBackend(settings.database_url)


async def _get_character(char_id: uuid.UUID) -> Character | None:
    async with await _backend.get_session() as session:
        result = await session.execute(select(Character).where(Character.id == char_id))
        return result.scalar_one_or_none()


def _character_to_entity_data(char: Character) -> dict[str, Any]:
    return {
        "name": char.name,
        "race": char.race,
        "discipline": char.discipline,
        "circle": char.circle,
        "personality": char.personality,
        "background": char.background,
        "goals": char.goals or "",
        "relationships": char.relationships or [],
        "skills": char.skills or [],
        "physical_description": char.physical_description or "",
    }


def build_twin_chat_page(session_state: gr.State) -> None:
    """Build the twin chat tab. Must be called inside a gr.Blocks context."""

    with gr.Tab("Twin Chat"):
        gr.Markdown("## Digital Twin Conversation")
        gr.Markdown(
            "Select a character and speak *as* them or speak *to* them. "
            "The twin responds in-character based on their personality and background."
        )

        with gr.Row():
            twin_char_selector = gr.Dropdown(
                label="Character",
                choices=[],
                value=None,
                interactive=True,
                scale=3,
            )
            twin_refresh_btn = gr.Button("↻", scale=1, min_width=60)

        twin_char_info = gr.Markdown("*Select a character to begin.*")

        chatbot = gr.Chatbot(
            label="Conversation",
            height=420,
        )

        with gr.Row():
            prompt_box = gr.Textbox(
                label="Your message",
                placeholder="What do you say or ask?",
                lines=2,
                scale=4,
                interactive=True,
            )
            with gr.Column(scale=1, min_width=120):
                send_btn = gr.Button("Send", variant="primary", interactive=True)
                suggest_btn = gr.Button("Suggest Responses", interactive=True)

        suggestions_box = gr.Radio(
            label="Suggested responses (pick one or write your own above)",
            choices=[],
            visible=False,
            interactive=True,
        )

        explain_btn = gr.Button("Why this response?", visible=False, interactive=True)
        explain_out = gr.Markdown("", visible=False)

        clear_btn = gr.Button("Clear conversation", size="sm")
        status_md = gr.Markdown("")

        # ── State: current character id ───────────────────────────────────
        selected_char_id: gr.State = gr.State(value=None)
        last_suggestion: gr.State = gr.State(value="")

        # ── Helpers ───────────────────────────────────────────────────────

        async def _load_char_choices(state: CampaignSession | None) -> dict[str, Any]:
            if state is None:
                return gr.update(choices=[], value=None)
            async with await _backend.get_session() as session:
                rows = await session.execute(
                    select(Character).where(
                        Character.campaign_id == state.campaign_id,
                        Character.player_display_name == state.display_name,
                    )
                )
                chars = list(rows.scalars().all())
            choices = [(c.name, str(c.id)) for c in chars]
            return gr.update(choices=choices, value=choices[0][1] if choices else None)

        async def on_char_selected(char_id: str | None) -> tuple[str, Any]:
            if not char_id:
                return "*No character selected.*", None
            char = await _get_character(uuid.UUID(char_id))
            if char is None:
                return "*Character not found.*", None
            info = (
                f"**{char.name}** — {char.race} {char.discipline} (Circle {char.circle})\n\n"
                f"*{char.personality}*"
            )
            return info, char_id

        async def on_send(
            state: CampaignSession | None,
            char_id_val: str | None,
            user_msg: str,
            history: list[dict[str, Any]],
        ) -> tuple[list[dict[str, Any]], str, str]:
            if state is None:
                return history, "", "Error: not in a campaign session."
            if not char_id_val:
                return history, user_msg, "Select a character first."
            if not user_msg.strip():
                return history, "", ""
            if not state.ai_available:
                return history, user_msg, "AI features unavailable in degraded mode."

            char = await _get_character(uuid.UUID(char_id_val))
            if char is None:
                return history, user_msg, "Character not found."

            from agents.twin.agent import get_or_create_twin, run_twin_turn
            from llm.providers.ollama import OllamaProvider

            try:
                async with await _backend.get_session() as session:
                    twin = await get_or_create_twin(
                        entity_type="character",
                        entity_id=char.id,
                        campaign_id=char.campaign_id,
                        db_session=session,
                    )
                    response, _ = await run_twin_turn(
                        user_message=user_msg.strip(),
                        twin_record=twin,
                        entity_type="character",
                        entity_data=_character_to_entity_data(char),
                        llm_provider=OllamaProvider(),
                        db_session=session,
                    )
            except ProviderUnavailableError:
                return history, user_msg, "AI is currently unreachable. Try again later."

            updated = list(history) + [
                {"role": "user", "content": user_msg.strip()},
                {"role": "assistant", "content": response},
            ]
            return updated, "", ""

        async def on_suggest(
            state: CampaignSession | None,
            char_id_val: str | None,
            situation: str,
            history: list[dict[str, Any]],
        ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], str]:
            empty_radio = gr.update(choices=[], visible=False)
            empty_explain = gr.update(visible=False)
            empty_explain_out = gr.update(value="", visible=False)
            if state is None or not char_id_val or not situation.strip():
                return empty_radio, empty_explain, empty_explain_out, gr.update(), ""
            if not state.ai_available:
                return empty_radio, empty_explain, empty_explain_out, gr.update(), "AI unavailable."

            char = await _get_character(uuid.UUID(char_id_val))
            if char is None:
                return empty_radio, empty_explain, empty_explain_out, gr.update(), "Character not found."

            from agents.twin.agent import DigitalTwinAgent
            from llm.providers.ollama import OllamaProvider

            agent = DigitalTwinAgent(
                entity_type="character",
                entity_data=_character_to_entity_data(char),
                llm_provider=OllamaProvider(),
            )
            try:
                result = await agent.suggest(situation.strip(), history)
            except ProviderUnavailableError:
                return empty_radio, empty_explain, empty_explain_out, gr.update(), "AI unreachable."

            choices = [
                f"[{s.tone}] {s.text}" for s in result.suggestions
            ]
            first = result.suggestions[0].text if result.suggestions else ""
            return (
                gr.update(choices=choices, value=choices[0] if choices else None, visible=True),
                gr.update(visible=True),
                gr.update(value="", visible=False),
                gr.update(value=first),
                "",
            )

        async def on_suggestion_pick(
            picked: str | None,
        ) -> tuple[str, str]:
            if not picked:
                return "", ""
            # Strip the [tone] prefix if present
            text = picked
            if picked.startswith("[") and "] " in picked:
                text = picked.split("] ", 1)[1]
            return text, text

        async def on_explain(
            state: CampaignSession | None,
            char_id_val: str | None,
            suggestion: str,
        ) -> dict[str, Any]:
            if not state or not char_id_val or not suggestion:
                return gr.update(value="No suggestion to explain.", visible=True)
            if not state.ai_available:
                return gr.update(value="AI unavailable.", visible=True)

            char = await _get_character(uuid.UUID(char_id_val))
            if char is None:
                return gr.update(value="Character not found.", visible=True)

            from agents.twin.agent import DigitalTwinAgent
            from llm.providers.ollama import OllamaProvider

            agent = DigitalTwinAgent(
                entity_type="character",
                entity_data=_character_to_entity_data(char),
                llm_provider=OllamaProvider(),
            )
            try:
                explanation = await agent.explain_suggestion(suggestion, [])
            except ProviderUnavailableError:
                return gr.update(value="AI unreachable.", visible=True)

            return gr.update(value=f"**Why this response?**\n\n{explanation}", visible=True)

        def on_clear() -> tuple[list[Any], str, str]:
            return [], "", ""

        # ── Wire events ───────────────────────────────────────────────────

        session_state.change(_load_char_choices, inputs=[session_state], outputs=[twin_char_selector])
        twin_refresh_btn.click(_load_char_choices, inputs=[session_state], outputs=[twin_char_selector])

        twin_char_selector.change(
            on_char_selected,
            inputs=[twin_char_selector],
            outputs=[twin_char_info, selected_char_id],
        )

        send_btn.click(
            on_send,
            inputs=[session_state, selected_char_id, prompt_box, chatbot],
            outputs=[chatbot, prompt_box, status_md],
        )
        prompt_box.submit(
            on_send,
            inputs=[session_state, selected_char_id, prompt_box, chatbot],
            outputs=[chatbot, prompt_box, status_md],
        )

        suggest_btn.click(
            on_suggest,
            inputs=[session_state, selected_char_id, prompt_box, chatbot],
            outputs=[suggestions_box, explain_btn, explain_out, prompt_box, status_md],
        )

        suggestions_box.change(
            on_suggestion_pick,
            inputs=[suggestions_box],
            outputs=[prompt_box, last_suggestion],
        )

        explain_btn.click(
            on_explain,
            inputs=[session_state, selected_char_id, last_suggestion],
            outputs=[explain_out],
        )

        clear_btn.click(on_clear, outputs=[chatbot, prompt_box, status_md])