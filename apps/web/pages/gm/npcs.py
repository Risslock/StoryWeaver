"""GM NPC management tab — create, edit, and chat with NPC digital twins."""

from __future__ import annotations

import uuid
from typing import Any

import gradio as gr
from core.config import settings
from core.errors import ProviderUnavailableError
from core.models import NPC
from core.schemas import CampaignSession, NPCSchema
from sqlalchemy import func, select
from storage.sqlite.adapter import SQLiteBackend
from components.image_display import build_portrait_display

_backend = SQLiteBackend(settings.database_url)


async def _load_npcs(campaign_id: uuid.UUID) -> list[NPC]:
    async with await _backend.get_session() as session:
        result = await session.execute(
            select(NPC).where(NPC.campaign_id == campaign_id)
        )
        return list(result.scalars().all())


async def _save_npc(campaign_id: uuid.UUID, data: dict[str, Any]) -> NPC:
    async with await _backend.get_session() as session:
        result = await session.execute(
            select(NPC).where(
                NPC.campaign_id == campaign_id,
                func.lower(NPC.name) == data["name"].lower(),
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            for k, v in data.items():
                if k not in ("id", "created_at", "campaign_id"):
                    setattr(existing, k, v)
            await session.commit()
            await session.refresh(existing)
            return existing
        npc = NPC(id=uuid.uuid4(), campaign_id=campaign_id, **data)
        session.add(npc)
        await session.commit()
        await session.refresh(npc)
        return npc


async def _update_npc(npc_id: uuid.UUID, updates: dict[str, Any]) -> NPC | None:
    async with await _backend.get_session() as session:
        result = await session.execute(select(NPC).where(NPC.id == npc_id))
        npc = result.scalar_one_or_none()
        if npc is None:
            return None
        for k, v in updates.items():
            setattr(npc, k, v)
        await session.commit()
        await session.refresh(npc)
        return npc


def _render_npc_sheet(npc: NPC) -> str:
    schema = NPCSchema.model_validate(npc)
    visibility = "Visible to players" if schema.is_visible_to_players else "Hidden from players"
    return f"""## {schema.name}
*{schema.role or "Unknown role"} · {schema.race or "Unknown race"} · Circle {schema.circle}*

**Visibility**: {visibility}

---

### Personality
{schema.personality or "—"}

### Background
{schema.background or "—"}

### Physical Description
{schema.physical_description or "—"}

### GM Notes (private)
{schema.gm_notes or "—"}
"""


def _npc_to_entity_data(npc: NPC) -> dict[str, Any]:
    return {
        "name": npc.name,
        "race": npc.race or "",
        "discipline": npc.discipline or "",
        "circle": npc.circle,
        "personality": npc.personality or "",
        "background": npc.background or "",
        "goals": "",
        "relationships": [],
        "skills": npc.skills or [],
        "physical_description": npc.physical_description or "",
    }


def build_npc_page(session_state: gr.State) -> None:
    """Build the GM NPC management tab. Must be called inside a gr.Blocks context."""

    with gr.Tab("NPCs"):
        gr.Markdown("## NPC Management")

        with gr.Row():
            npc_selector = gr.Dropdown(
                label="Select NPC",
                choices=[],
                value=None,
                interactive=True,
                scale=3,
            )
            refresh_btn = gr.Button("↻ Refresh", scale=1)

        npc_portrait = build_portrait_display("NPC Portrait")
        npc_sheet = gr.Markdown("*Select an NPC or create a new one below.*")

        with gr.Row():
            visibility_toggle = gr.Checkbox(
                label="Visible to players",
                value=False,
                interactive=True,
            )
            toggle_btn = gr.Button("Apply Visibility", scale=1)
            toggle_status = gr.Markdown("")

        gr.Markdown("---")
        gr.Markdown("### NPC Twin Chat")

        twin_chatbot = gr.Chatbot(label="NPC Conversation", height=300)
        with gr.Row():
            twin_prompt = gr.Textbox(
                label="Speak to or as the NPC",
                placeholder="What does this NPC say or do?",
                lines=2,
                scale=4,
            )
            twin_send_btn = gr.Button("Send", variant="primary", scale=1)

        twin_status = gr.Markdown("")

        gr.Markdown("---")
        gr.Markdown("### Create / Edit NPC")

        with gr.Group():
            with gr.Row():
                npc_name = gr.Textbox(label="Name *", placeholder="Vorgath the Merchant")
                npc_role = gr.Textbox(label="Role", placeholder="merchant, villain, ally…")
            with gr.Row():
                npc_race = gr.Textbox(label="Race", placeholder="Ork, Elf, Troll…")
                npc_discipline = gr.Textbox(label="Discipline", placeholder="optional")
                npc_circle = gr.Slider(label="Circle", minimum=0, maximum=15, step=1, value=0)

        with gr.Group():
            npc_personality = gr.Textbox(
                label="Personality *",
                placeholder="How does this NPC think, speak, and act?",
                lines=2,
            )
            npc_background = gr.Textbox(
                label="Background *",
                placeholder="Who are they, and what shaped them?",
                lines=3,
            )
            npc_physical = gr.Textbox(
                label="Physical Description",
                placeholder="Used for portrait generation.",
                lines=2,
            )
            npc_gm_notes = gr.Textbox(
                label="GM Notes (private — never shown to players)",
                placeholder="Hidden motivations, secrets, plot hooks…",
                lines=3,
            )

        with gr.Row():
            save_btn = gr.Button("Save NPC", variant="primary")
            save_status = gr.Markdown("")

        with gr.Row():
            portrait_btn = gr.Button("Generate Portrait", variant="secondary", interactive=False)
            portrait_status = gr.Markdown("")

        # ── Internal state ────────────────────────────────────────────────
        selected_npc_id: gr.State = gr.State(value=None)

        # ── Helpers ───────────────────────────────────────────────────────

        async def load_npc_list(state: CampaignSession | None) -> dict[str, Any]:
            if state is None:
                return gr.update(choices=[], value=None)
            npcs = await _load_npcs(state.campaign_id)
            choices = [(n.name, str(n.id)) for n in npcs]
            return gr.update(choices=choices, value=choices[0][1] if choices else None)

        async def on_select_npc(npc_id: str | None) -> tuple[str | None, str, bool, Any]:
            if not npc_id:
                return None, "*No NPC selected.*", False, None
            async with await _backend.get_session() as session:
                result = await session.execute(
                    select(NPC).where(NPC.id == uuid.UUID(npc_id))
                )
                npc = result.scalar_one_or_none()
            if npc is None:
                return None, "*NPC not found.*", False, None
            return npc.portrait_url or None, _render_npc_sheet(npc), npc.is_visible_to_players, npc_id

        async def on_generate_portrait(
            state: CampaignSession | None,
            npc_id_val: str | None,
        ) -> tuple[str | None, str]:
            if state is None or not npc_id_val:
                return None, "Select an NPC first."
            if not state.ai_available:
                return None, "AI features unavailable in degraded mode."

            async with await _backend.get_session() as session:
                result = await session.execute(
                    select(NPC).where(NPC.id == uuid.UUID(npc_id_val))
                )
                npc = result.scalar_one_or_none()
                if npc is None:
                    return None, "NPC not found."

            if not (npc.physical_description or "").strip():
                return None, "Add a physical description to the NPC first."

            from imagegen.factory import get_image_provider
            from imagegen.interface import (
                ImageGenRequest,
                PORTRAIT_PROMPT_PREFIX,
                PORTRAIT_NEGATIVE_PROMPT,
            )

            prompt = (
                f"{PORTRAIT_PROMPT_PREFIX}, "
                f"{npc.name}, {npc.race or 'character'}, {npc.role or ''}, "
                f"{npc.physical_description}"
            )
            request = ImageGenRequest(
                prompt=prompt,
                negative_prompt=PORTRAIT_NEGATIVE_PROMPT,
                entity_id=npc.id,
            )

            provider = get_image_provider()
            response = await provider.generate(request)

            if response.error:
                return None, f"Portrait generation failed: {response.error}"

            await _update_npc(npc.id, {"portrait_url": response.image_url})
            return response.image_url, "Portrait generated!"

        async def on_toggle_visibility(
            state: CampaignSession | None,
            npc_id_val: str | None,
            is_visible: bool,
        ) -> str:
            if state is None or not npc_id_val:
                return "Select an NPC first."
            npc = await _update_npc(uuid.UUID(npc_id_val), {"is_visible_to_players": is_visible})
            if npc is None:
                return "NPC not found."
            status = "visible to players" if npc.is_visible_to_players else "hidden from players"
            return f"✓ **{npc.name}** is now {status}."

        async def on_twin_send(
            state: CampaignSession | None,
            npc_id_val: str | None,
            user_msg: str,
            history: list[dict[str, Any]],
        ) -> tuple[list[dict[str, Any]], str, str]:
            if state is None:
                return history, "", "Error: not in a campaign session."
            if not npc_id_val:
                return history, user_msg, "Select an NPC first."
            if not user_msg.strip():
                return history, "", ""
            if not state.ai_available:
                return history, user_msg, "AI features unavailable in degraded mode."

            async with await _backend.get_session() as session:
                result = await session.execute(
                    select(NPC).where(NPC.id == uuid.UUID(npc_id_val))
                )
                npc = result.scalar_one_or_none()
                if npc is None:
                    return history, user_msg, "NPC not found."

                from agents.twin.agent import get_or_create_twin, run_twin_turn
                from llm.providers.ollama import OllamaProvider

                try:
                    twin = await get_or_create_twin(
                        entity_type="npc",
                        entity_id=npc.id,
                        campaign_id=npc.campaign_id,
                        db_session=session,
                    )
                    response, _ = await run_twin_turn(
                        user_message=user_msg.strip(),
                        twin_record=twin,
                        entity_type="npc",
                        entity_data=_npc_to_entity_data(npc),
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

        async def on_save(
            state: CampaignSession | None,
            name: str,
            role: str,
            race: str,
            discipline: str,
            circle: int,
            personality: str,
            background: str,
            physical: str,
            gm_notes: str,
        ) -> tuple[str, dict[str, Any]]:
            if state is None:
                return "Error: not in a campaign session.", gr.update()
            if not name.strip():
                return "NPC name is required.", gr.update()
            if not personality.strip():
                return "Personality is required for the NPC twin.", gr.update()
            if not background.strip():
                return "Background is required for the NPC twin.", gr.update()

            data: dict[str, Any] = {
                "name": name.strip(),
                "role": role.strip() or None,
                "race": race.strip() or None,
                "discipline": discipline.strip() or None,
                "circle": int(circle),
                "personality": personality.strip(),
                "background": background.strip(),
                "physical_description": physical.strip() or None,
                "gm_notes": gm_notes.strip() or None,
                "attributes": {},
                "derived_stats": {},
                "talents": [],
                "skills": [],
                "is_visible_to_players": False,
            }

            await _save_npc(state.campaign_id, data)
            npcs = await _load_npcs(state.campaign_id)
            choices = [(n.name, str(n.id)) for n in npcs]
            return (
                f"✓ NPC **{data['name']}** saved!",
                gr.update(choices=choices, value=choices[-1][1] if choices else None),
            )

        # ── Wire events ───────────────────────────────────────────────────

        def _update_portrait_btn(state: CampaignSession | None) -> dict[str, Any]:
            ai_ok = state.ai_available if state is not None else False
            return gr.update(interactive=ai_ok)

        session_state.change(load_npc_list, inputs=[session_state], outputs=[npc_selector])
        session_state.change(_update_portrait_btn, inputs=[session_state], outputs=[portrait_btn])
        refresh_btn.click(load_npc_list, inputs=[session_state], outputs=[npc_selector])

        npc_selector.change(
            on_select_npc,
            inputs=[npc_selector],
            outputs=[npc_portrait, npc_sheet, visibility_toggle, selected_npc_id],
        )

        toggle_btn.click(
            on_toggle_visibility,
            inputs=[session_state, selected_npc_id, visibility_toggle],
            outputs=[toggle_status],
        )

        twin_send_btn.click(
            on_twin_send,
            inputs=[session_state, selected_npc_id, twin_prompt, twin_chatbot],
            outputs=[twin_chatbot, twin_prompt, twin_status],
        )
        twin_prompt.submit(
            on_twin_send,
            inputs=[session_state, selected_npc_id, twin_prompt, twin_chatbot],
            outputs=[twin_chatbot, twin_prompt, twin_status],
        )

        save_btn.click(
            on_save,
            inputs=[
                session_state,
                npc_name, npc_role, npc_race, npc_discipline, npc_circle,
                npc_personality, npc_background, npc_physical, npc_gm_notes,
            ],
            outputs=[save_status, npc_selector],
        )
        portrait_btn.click(
            on_generate_portrait,
            inputs=[session_state, selected_npc_id],
            outputs=[npc_portrait, portrait_status],
        )