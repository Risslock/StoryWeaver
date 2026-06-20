"""Auth-first player campaign join screen."""

from __future__ import annotations

from typing import Any, NamedTuple

import gradio as gr
from core.models import Campaign
from core.schemas import CampaignSession, UserInfo
from llm.providers.ollama import OllamaProvider
from services.db import get_backend
from storage.users import (
    get_campaign_by_join_code,
    get_campaigns_for_player,
    get_or_create_player,
)


class PlayerJoinRefs(NamedTuple):
    joined_table: gr.Dataframe
    joined_codes: gr.State
    join_btn: gr.Button
    join_code_in: gr.Textbox
    join_status: gr.Markdown
    rejoin_status: gr.Markdown


async def load_joined_campaigns(
    user: UserInfo | None,
) -> tuple[Any, list[str]]:
    """Return (dataframe update, join_codes list) for the given user."""
    if user is None:
        return gr.update(value=[]), []
    backend = get_backend()
    async with await backend.get_session() as session:
        campaigns = await get_campaigns_for_player(session, user.user_id)
    rows = [[c.name, c.join_code] for c in campaigns]
    codes = [c.join_code for c in campaigns]
    return gr.update(value=rows), codes


async def _build_session(campaign: Campaign, user: UserInfo) -> CampaignSession:
    ai_available = await OllamaProvider().health_check()
    backend = get_backend()
    async with await backend.get_session() as session:
        await get_or_create_player(
            session,
            campaign_id=campaign.id,
            user_id=user.user_id,
            username=user.username,
        )
    return CampaignSession(
        campaign_id=campaign.id,
        display_name=user.username,
        role="player",
        user_id=user.user_id,
        join_code=campaign.join_code,
        ai_available=ai_available,
    )


async def on_join(
    code: str,
    user: UserInfo | None,
) -> tuple[str, CampaignSession | None]:
    if user is None:
        return "Sign in before joining a campaign.", None
    code = code.strip().upper()
    if not code:
        return "Enter the join code your GM gave you.", None

    backend = get_backend()
    async with await backend.get_session() as session:
        campaign = await get_campaign_by_join_code(session, code)
    if campaign is None:
        return "No campaign found with that join code.", None
    if campaign.archived:
        return "No campaign found with that join code.", None

    campaign_session = await _build_session(campaign, user)
    return f"Joined! Welcome, **{user.username}**.", campaign_session


async def on_row_select(
    user: UserInfo | None,
    codes: list[str],
    evt: gr.SelectData,
) -> tuple[str, CampaignSession | None]:
    if user is None:
        return "Sign in to rejoin a campaign.", None
    row_idx = evt.index[0]
    if row_idx >= len(codes):
        return "Campaign not found.", None
    join_code = codes[row_idx]

    backend = get_backend()
    async with await backend.get_session() as session:
        campaign = await get_campaign_by_join_code(session, join_code)
    if campaign is None or campaign.archived:
        return "Campaign no longer available.", None

    campaign_session = await _build_session(campaign, user)
    return f"Rejoining **{campaign.name}**…", campaign_session


def build_player_join_page(
    session_state: gr.State, user_state: gr.State
) -> PlayerJoinRefs:
    """Build the player join screen. Must be called inside a gr.Blocks context."""

    joined_codes: gr.State = gr.State(value=[])

    gr.Markdown("## Join a Campaign")

    gr.Markdown("### Your Campaigns")
    gr.Markdown("*Click a campaign below to re-enter it instantly.*")

    joined_table = gr.Dataframe(
        headers=["Campaign Name", "Join Code"],
        datatype=["str", "str"],
        value=[],
        interactive=False,
        label=None,
        elem_id="joined-campaigns-table",
    )
    rejoin_status = gr.Markdown("", elem_id="rejoin-status")

    gr.Markdown("---")

    gr.Markdown("### Join a New Campaign")
    gr.Markdown("Ask your GM for the 6-character join code.")

    join_code_in = gr.Textbox(
        label="Join Code",
        placeholder="A3KP72",
        max_lines=1,
        elem_id="player-join-code-input",
    )
    join_btn = gr.Button(
        "Join Campaign",
        variant="primary",
        elem_id="player-join-btn",
    )
    join_status = gr.Markdown("", elem_id="player-join-status")

    return PlayerJoinRefs(
        joined_table=joined_table,
        joined_codes=joined_codes,
        join_btn=join_btn,
        join_code_in=join_code_in,
        join_status=join_status,
        rejoin_status=rejoin_status,
    )
