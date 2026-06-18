"""Campaign create and join flow."""

from __future__ import annotations

import random
import string
import uuid
from typing import Any

import gradio as gr
from sqlalchemy import select

from core.config import settings
from core.errors import CampaignJoinError
from core.models import Campaign
from core.schemas import CampaignSession
from llm.providers.ollama import OllamaProvider
from storage.sqlite.adapter import SQLiteBackend

_backend = SQLiteBackend(settings.database_url)


def _generate_join_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


async def _ensure_db() -> None:
    await _backend.initialize_db()


async def create_campaign(name: str, gm_display_name: str) -> tuple[str, Any]:
    """Create a new campaign and return (join_code, CampaignSession)."""
    if not name.strip() or not gm_display_name.strip():
        raise CampaignJoinError("Campaign name and GM display name are required.")

    await _ensure_db()
    session = await _backend.get_session()
    async with session:
        join_code = _generate_join_code()
        campaign = Campaign(
            id=uuid.uuid4(),
            name=name.strip(),
            join_code=join_code,
            gm_display_name=gm_display_name.strip(),
        )
        session.add(campaign)
        await session.commit()
        ai_available = await OllamaProvider().health_check()
        state = CampaignSession(
            campaign_id=campaign.id,
            display_name=gm_display_name.strip(),
            role="gm",
            join_code=join_code,
            ai_available=ai_available,
        )
        return join_code, state


async def join_campaign(join_code: str, display_name: str) -> tuple[str, Any]:
    """Join an existing campaign and return (role, CampaignSession)."""
    if not join_code.strip() or not display_name.strip():
        raise CampaignJoinError("Join code and display name are required.")

    await _ensure_db()
    session = await _backend.get_session()
    async with session:
        result = await session.execute(
            select(Campaign).where(Campaign.join_code == join_code.strip().upper())
        )
        campaign = result.scalar_one_or_none()
        if campaign is None:
            raise CampaignJoinError(f"No campaign found with join code '{join_code}'.")

        role: str = (
            "gm"
            if display_name.strip().lower() == campaign.gm_display_name.lower()
            else "player"
        )
        ai_available = await OllamaProvider().health_check()
        state = CampaignSession(
            campaign_id=campaign.id,
            display_name=display_name.strip(),
            role=role,  # type: ignore[arg-type]
            join_code=campaign.join_code,
            ai_available=ai_available,
        )
        return role, state


def build_landing(session_state: gr.State) -> None:
    """Build the landing tab UI.

    Handlers return the updated session state through Gradio's output system so
    the session_state.change() event fires and the app navigates to the correct
    player/GM dashboard.
    """
    gr.Markdown("# StoryWeaver")
    gr.Markdown(
        "An AI-assisted narrative companion for tabletop RPGs. "
        "Create a campaign or join an existing one with a join code."
    )

    with gr.Tab("Create Campaign"):
        camp_name = gr.Textbox(label="Campaign Name", placeholder="The Kaer of Shadows")
        gm_name = gr.Textbox(label="Your Display Name (GM)", placeholder="Dungeon Master")
        create_btn = gr.Button("Create Campaign", variant="primary")
        create_out = gr.Textbox(label="Join Code", interactive=False)
        create_status = gr.Markdown("")

        async def on_create(name: str, gm: str) -> tuple[str, str, Any]:
            try:
                code, state = await create_campaign(name, gm)
                return (
                    code,
                    f"Campaign created! Share this code with your players: **{code}**",
                    state,
                )
            except CampaignJoinError as exc:
                return "", f"Error: {exc}", None

        create_btn.click(
            on_create,
            inputs=[camp_name, gm_name],
            outputs=[create_out, create_status, session_state],
        )

    with gr.Tab("Join Campaign"):
        join_code_in = gr.Textbox(label="Join Code", placeholder="ABC12345")
        join_name = gr.Textbox(label="Your Display Name", placeholder="Gandalf")
        join_btn = gr.Button("Join", variant="primary")
        join_status = gr.Markdown("")

        async def on_join(code: str, name: str) -> tuple[str, Any]:
            try:
                role, state = await join_campaign(code, name)
                return f"Joined as **{role.upper()}**. Welcome, {name}!", state
            except CampaignJoinError as exc:
                return f"Error: {exc}", None

        join_btn.click(
            on_join,
            inputs=[join_code_in, join_name],
            outputs=[join_status, session_state],
        )