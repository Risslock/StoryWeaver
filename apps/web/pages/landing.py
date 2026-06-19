"""Player campaign join flow."""

from __future__ import annotations

from typing import Any

import gradio as gr
from core.config import settings
from core.errors import CampaignJoinError
from core.models import Campaign
from core.schemas import CampaignSession
from llm.providers.ollama import OllamaProvider
from sqlalchemy import func, select
from storage.sqlite.adapter import SQLiteBackend
from storage.users import get_or_create_player

_backend = SQLiteBackend(settings.database_url)


def get_backend() -> SQLiteBackend:
    """Return the module-level storage backend singleton."""
    return _backend


async def join_campaign(
    campaign_name: str,
    join_code: str,
    player_name: str,
) -> tuple[str, Any]:
    """Join an existing campaign by name + join code, returning (role, CampaignSession).

    Creates or restores the Player record. If Player.character_id is set, the
    character is accessible in the returned session via the existing character
    display logic (loaded by player_display_name in character.py).
    """
    campaign_name = campaign_name.strip()
    join_code = join_code.strip().upper()
    player_name = player_name.strip()

    if not campaign_name or not join_code or not player_name:
        raise CampaignJoinError(
            "Campaign name, join code, and player name are all required."
        )

    async with await _backend.get_session() as session:
        result = await session.execute(
            select(Campaign).where(
                func.lower(Campaign.name) == campaign_name.lower(),
                Campaign.join_code == join_code,
            )
        )
        campaign = result.scalar_one_or_none()
        if campaign is None:
            raise CampaignJoinError(
                "No campaign found with that name and join code."
            )

        await get_or_create_player(session, campaign.id, player_name)

        ai_available = await OllamaProvider().health_check()
        state = CampaignSession(
            campaign_id=campaign.id,
            display_name=player_name,
            role="player",
            join_code=campaign.join_code,
            ai_available=ai_available,
        )
        return "player", state


def build_landing(session_state: gr.State) -> None:
    """Build the player join tab UI inside the current Blocks context.

    Players enter campaign name + join code + player name to join or rejoin
    a campaign session. No campaign creation — GMs create campaigns from the
    Campaign Dashboard.
    """
    gr.Markdown("### Join a Campaign")
    gr.Markdown(
        "Ask your GM for the campaign name and join code, then enter "
        "your player name below."
    )

    join_campaign_name = gr.Textbox(
        label="Campaign Name", placeholder="The Iron Crown"
    )
    join_code_in = gr.Textbox(label="Join Code", placeholder="A3KP72")
    join_name = gr.Textbox(label="Your Player Name", placeholder="Kira Stonefist")
    join_btn = gr.Button("Join Campaign", variant="primary")
    join_status = gr.Markdown("")

    async def on_join(
        campaign_nm: str,
        code: str,
        name: str,
    ) -> tuple[str, Any]:
        try:
            _, state = await join_campaign(campaign_nm, code, name)
            return f"Joined! Welcome, **{name}**.", state
        except CampaignJoinError as exc:
            return f"Error: {exc}", None

    join_btn.click(
        on_join,
        inputs=[join_campaign_name, join_code_in, join_name],
        outputs=[join_status, session_state],
    )
