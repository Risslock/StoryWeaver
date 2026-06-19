"""Gradio app factory for StoryWeaver.

Multi-user session isolation model
───────────────────────────────────
1. Per-tab state: two gr.State objects per browser tab.
   - user_state: UserInfo | None — who is signed in.
   - session_state: CampaignSession | None — active campaign.
   Gradio 4.x guarantees that gr.State is isolated per browser tab — no
   state object is ever shared between concurrent user connections.

2. Navigation state machine (driven by user_state + session_state):
   None / None   → auth_col    (Sign In / Create Account)
   user / None   → admin_col   (campaign dashboard + player join)
   user / "gm"   → gm_col
   user / "player" → player_col

3. Concurrent DB writes: SQLiteBackend sets PRAGMA journal_mode=WAL at
   connection-open time (packages/storage/sqlite/adapter.py).
"""

from __future__ import annotations

from typing import Any

import gradio as gr
from components.banner import build_banner
from core.schemas import CampaignSession, UserInfo
from pages.admin.campaigns import (
    CampaignPageRefs,
    build_campaigns_page,
    load_campaigns_for_user,
)
from pages.auth import build_auth_page
from pages.gm.characters import build_characters_page
from pages.gm.history import build_gm_history_page
from pages.gm.npcs import build_npc_page
from pages.gm.session_plan import build_session_plan_page
from pages.gm.world_notes import build_world_notes_page
from pages.landing import build_landing, get_backend
from pages.player.character import build_character_page
from pages.player.history import build_player_history_page
from pages.player.twin_chat import build_twin_chat_page


async def _startup_verify() -> None:
    """Verify WAL mode is active — schema must already exist via Alembic."""
    db = get_backend()
    if not await db.verify_wal_mode():
        raise RuntimeError(
            "SQLite WAL mode is not active. "
            "Concurrent reads and writes may block each other. "
            "Ensure the database URL points to a file-based SQLite database."
        )


def create_app() -> gr.Blocks:
    with gr.Blocks(title="StoryWeaver") as app:
        user_state: gr.State = gr.State(value=None)
        session_state: gr.State = gr.State(value=None)

        banner = build_banner()

        # ── Auth screen (default — shown until sign-in) ───────────────────────
        with gr.Column(visible=True) as auth_col:
            build_auth_page(user_state)

        # ── Campaigns admin dashboard + player join ───────────────────────────
        with gr.Column(visible=False) as admin_col:
            campaign_refs: CampaignPageRefs = build_campaigns_page(
                session_state, user_state
            )
            gr.Markdown("---")
            build_landing(session_state)

        # ── Player dashboard ──────────────────────────────────────────────────
        with gr.Column(visible=False) as player_col:
            gr.Markdown("# StoryWeaver — Player Dashboard")
            with gr.Tabs():
                build_character_page(session_state)
                build_twin_chat_page(session_state)
                build_player_history_page(session_state)

        # ── GM dashboard ──────────────────────────────────────────────────────
        with gr.Column(visible=False) as gm_col:
            gr.Markdown("# StoryWeaver — GM Dashboard")
            gm_join_code = gr.Textbox(
                label="Campaign Join Code — share this with your players",
                interactive=False,
                buttons=["copy"],
            )
            with gr.Tabs():
                build_characters_page(session_state)
                build_npc_page(session_state)
                build_gm_history_page(session_state)
                build_world_notes_page(session_state)
                build_session_plan_page(session_state)

        # ── Navigation ────────────────────────────────────────────────────────
        def _navigate(
            user: UserInfo | None, session: CampaignSession | None
        ) -> tuple[Any, ...]:
            """Return visibility/value updates for all panels."""
            if user is None and session is None:
                return (
                    gr.update(visible=True),  # auth_col
                    gr.update(visible=False),  # banner
                    gr.update(visible=False),  # admin_col
                    gr.update(visible=False),  # player_col
                    gr.update(visible=False),  # gm_col
                    gr.update(value=""),  # gm_join_code
                )
            if user is None and session is not None:
                # Player joined via join code — no User account, session only
                show_banner = not session.ai_available
                return (
                    gr.update(visible=False),
                    gr.update(visible=show_banner),
                    gr.update(visible=False),
                    gr.update(visible=True),
                    gr.update(visible=False),
                    gr.update(value=""),
                )
            if session is None:
                return (
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=True),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(value=""),
                )
            show_banner = not session.ai_available
            if session.role == "gm":
                return (
                    gr.update(visible=False),
                    gr.update(visible=show_banner),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=True),
                    gr.update(value=session.join_code),
                )
            return (
                gr.update(visible=False),
                gr.update(visible=show_banner),
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(value=""),
            )

        _nav_outputs = [auth_col, banner, admin_col, player_col, gm_col, gm_join_code]

        user_state.change(
            _navigate,
            inputs=[user_state, session_state],
            outputs=_nav_outputs,
        )
        session_state.change(
            _navigate,
            inputs=[user_state, session_state],
            outputs=_nav_outputs,
        )

        # Load campaigns whenever the user signs in.
        user_state.change(
            load_campaigns_for_user,
            inputs=[user_state],
            outputs=[
                campaign_refs.table,
                campaign_refs.campaign_ids,
                campaign_refs.no_campaigns_msg,
            ],
        )

    return app


if __name__ == "__main__":
    import asyncio

    asyncio.run(_startup_verify())
    create_app().launch()
