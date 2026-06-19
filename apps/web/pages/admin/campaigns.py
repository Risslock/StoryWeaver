"""Admin campaign dashboard and campaign detail screens for authenticated GMs."""

from __future__ import annotations

import re
import secrets
import uuid
from typing import Any, NamedTuple

import gradio as gr
from core.models import Campaign
from core.schemas import CampaignSession, UserInfo
from llm.providers.ollama import OllamaProvider
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from storage.users import archive_campaign as _archive_campaign

from pages.landing import get_backend


class CampaignPageRefs(NamedTuple):
    """Component references returned to app.py for user_state wiring."""

    table: gr.Dataframe
    campaign_ids: gr.State
    no_campaigns_msg: gr.Markdown


def _generate_join_code() -> str:
    chars = re.sub(r"[^A-Z0-9]", "", secrets.token_urlsafe(16).upper())
    return chars[:6] if len(chars) >= 6 else _generate_join_code()


async def _fetch_campaigns(
    owner_id: uuid.UUID,
) -> tuple[list[list[str]], list[str]]:
    """Return (table_rows, campaign_id_list) for the given owner."""
    backend = get_backend()
    async with await backend.get_session() as session:
        result = await session.execute(
            select(Campaign)
            .where(Campaign.owner_id == owner_id, Campaign.archived.is_(False))
            .order_by(Campaign.created_at.desc())
        )
        campaigns = list(result.scalars().all())
    rows = [
        [c.name, c.join_code, c.created_at.strftime("%Y-%m-%d")]
        for c in campaigns
    ]
    ids = [str(c.id) for c in campaigns]
    return rows, ids


async def load_campaigns_for_user(
    user: UserInfo | None,
) -> tuple[Any, list[str], Any]:
    """Load campaigns when the user signs in; called from user_state.change()."""
    if user is None:
        return gr.update(value=[]), [], gr.update(visible=False)
    rows, ids = await _fetch_campaigns(user.user_id)
    return gr.update(value=rows), ids, gr.update(visible=len(rows) == 0)


def build_campaigns_page(
    session_state: gr.State, user_state: gr.State
) -> CampaignPageRefs:
    """Build the Campaign Dashboard and Detail screens.

    Returns CampaignPageRefs for the caller to wire user_state.change().
    """
    campaign_ids: gr.State = gr.State(value=[])
    selected_campaign_id: gr.State = gr.State(value=None)

    # ── Dashboard screen ──────────────────────────────────────────────────────
    with gr.Column(visible=True) as dashboard_col:
        gr.Markdown("## My Campaigns")

        new_campaign_btn = gr.Button("+ New Campaign", variant="secondary")

        with gr.Group(visible=False) as create_form:
            campaign_name_in = gr.Textbox(
                label="Campaign Name", placeholder="The Iron Crown"
            )
            game_system_in = gr.Dropdown(
                label="Game System",
                choices=["earthdawn_4e"],
                value="earthdawn_4e",
            )
            create_btn = gr.Button("Create", variant="primary")
            create_msg = gr.Markdown("")

        campaign_table = gr.Dataframe(
            headers=["Name", "Join Code", "Created"],
            datatype=["str", "str", "str"],
            value=[],
            interactive=False,
            label=None,
        )
        no_campaigns_msg = gr.Markdown(
            "*No campaigns yet — create one above.*", visible=False
        )

    # ── Campaign Detail screen ────────────────────────────────────────────────
    with gr.Column(visible=False) as detail_col:
        back_btn = gr.Button("← Back to Campaigns")
        detail_name = gr.Markdown("")
        detail_join_code = gr.Textbox(
            label="Join Code",
            interactive=False,
            buttons=["copy"],
        )
        detail_system = gr.Markdown("")
        detail_created = gr.Markdown("")
        with gr.Row():
            resume_btn = gr.Button("Resume Campaign →", variant="primary")
            archive_btn = gr.Button("Archive Campaign", variant="stop")

    # ── Event handlers ────────────────────────────────────────────────────────

    async def on_toggle_create_form() -> dict[str, Any]:
        return gr.update(visible=True)

    async def on_create_campaign(
        name: str,
        game_system: str,
        ids: list[str],
        user: UserInfo | None,
    ) -> tuple[Any, Any, Any, list[str]]:
        if user is None:
            return gr.update(), gr.update(), gr.update(value="Not signed in."), ids
        if not name.strip():
            return (
                gr.update(),
                gr.update(),
                gr.update(value="Campaign name cannot be empty."),
                ids,
            )

        backend = get_backend()
        for _ in range(5):
            join_code = _generate_join_code()
            async with await backend.get_session() as session:
                try:
                    campaign = Campaign(
                        id=uuid.uuid4(),
                        name=name.strip(),
                        join_code=join_code,
                        gm_display_name=user.username,
                        game_system=game_system,
                        owner_id=user.user_id,
                    )
                    session.add(campaign)
                    await session.commit()
                    break
                except IntegrityError as exc:
                    await session.rollback()
                    err_str = str(exc).lower()
                    if "ix_campaigns_owner_name_lower" in err_str:
                        return (
                            gr.update(),
                            gr.update(),
                            gr.update(
                                value=(
                                    f"A campaign named '{name.strip()}'"
                                    " already exists."
                                )
                            ),
                            ids,
                        )
                    continue  # join_code collision — retry
        else:
            return (
                gr.update(),
                gr.update(),
                gr.update(value="Failed to generate a unique join code. Try again."),
                ids,
            )

        rows, new_ids = await _fetch_campaigns(user.user_id)
        return (
            gr.update(value=rows),
            gr.update(visible=False),
            gr.update(value=""),
            new_ids,
        )

    async def on_row_select(
        ids: list[str],
        evt: gr.SelectData,
    ) -> tuple[Any, ...]:
        row_idx = evt.index[0]
        if row_idx >= len(ids):
            return (None,) + (gr.update(),) * 7
        campaign_id_str: str = ids[row_idx]
        backend = get_backend()
        async with await backend.get_session() as session:
            result = await session.execute(
                select(Campaign).where(Campaign.id == uuid.UUID(campaign_id_str))
            )
            campaign = result.scalar_one_or_none()
        if campaign is None:
            return (None,) + (gr.update(),) * 7
        return (
            campaign_id_str,
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(value=f"## Campaign: {campaign.name}"),
            gr.update(value=campaign.join_code),
            gr.update(value=f"**Game System**: {campaign.game_system}"),
            gr.update(value=f"**Created**: {campaign.created_at.strftime('%Y-%m-%d')}"),
            gr.update(visible=False),
        )

    async def on_back() -> tuple[Any, Any]:
        return gr.update(visible=True), gr.update(visible=False)

    async def on_archive(
        campaign_id_str: str | None,
        user: UserInfo | None,
    ) -> tuple[Any, list[str], Any, Any]:
        if not campaign_id_str or user is None:
            return gr.update(), [], gr.update(), gr.update()
        backend = get_backend()
        async with await backend.get_session() as session:
            await _archive_campaign(session, uuid.UUID(campaign_id_str))
        rows, new_ids = await _fetch_campaigns(user.user_id)
        return (
            gr.update(value=rows),
            new_ids,
            gr.update(visible=True),   # dashboard_col
            gr.update(visible=False),  # detail_col
        )

    async def on_resume(
        campaign_id_str: str | None,
        user: UserInfo | None,
    ) -> CampaignSession | dict[str, Any]:
        if not campaign_id_str or user is None:
            return gr.update()
        backend = get_backend()
        async with await backend.get_session() as session:
            result = await session.execute(
                select(Campaign).where(
                    Campaign.id == uuid.UUID(campaign_id_str),
                    Campaign.owner_id == user.user_id,
                )
            )
            campaign = result.scalar_one_or_none()
        if campaign is None:
            return gr.update()
        ai_available = await OllamaProvider().health_check()
        return CampaignSession(
            campaign_id=campaign.id,
            display_name=user.username,
            role="gm",
            join_code=campaign.join_code,
            ai_available=ai_available,
        )

    # ── Wire events ───────────────────────────────────────────────────────────

    new_campaign_btn.click(
        on_toggle_create_form,
        inputs=[],
        outputs=[create_form],
    )

    create_btn.click(
        on_create_campaign,
        inputs=[campaign_name_in, game_system_in, campaign_ids, user_state],
        outputs=[campaign_table, create_form, create_msg, campaign_ids],
    )

    campaign_table.select(
        on_row_select,
        inputs=[campaign_ids],
        outputs=[
            selected_campaign_id,
            dashboard_col,
            detail_col,
            detail_name,
            detail_join_code,
            detail_system,
            detail_created,
            no_campaigns_msg,
        ],
    )

    back_btn.click(
        on_back,
        inputs=[],
        outputs=[dashboard_col, detail_col],
    )

    resume_btn.click(
        on_resume,
        inputs=[selected_campaign_id, user_state],
        outputs=[session_state],
    )

    archive_btn.click(
        on_archive,
        inputs=[selected_campaign_id, user_state],
        outputs=[campaign_table, campaign_ids, dashboard_col, detail_col],
    )

    return CampaignPageRefs(
        table=campaign_table,
        campaign_ids=campaign_ids,
        no_campaigns_msg=no_campaigns_msg,
    )
