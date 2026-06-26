# ruff: noqa: E402 — warnings filter must run before gradio/starlette is imported
"""Gradio app factory for StoryWeaver.

Multi-user session isolation model
───────────────────────────────────
1. Per-tab state: two gr.State objects per browser tab.
   - user_state: UserInfo | None — who is signed in.
   - session_state: CampaignSession | None — active campaign.
   Gradio 4.x guarantees that gr.State is isolated per browser tab — no
   state object is ever shared between concurrent user connections.

2. Navigation state machine (driven by user_state + session_state):
   None / None       → auth_col    (Sign In / Create Account)
   user / None       → hub_col     (My Campaigns (GM) | Join a Campaign (Player))
   user / "gm"       → gm_col
   user / "player"   → player_col

3. Concurrent DB writes: SQLiteBackend sets PRAGMA journal_mode=WAL at
   connection-open time (packages/storage/sqlite/adapter.py).
"""

from __future__ import annotations

import logging
import os
import warnings

warnings.filterwarnings(  # must run before gradio imports starlette
    "ignore",
    message=".*HTTP_422_UNPROCESSABLE_ENTITY.*",
)

# Configure package loggers from LOG_LEVEL env var so INFO messages from rag.*,
# llm.*, and core.* are visible regardless of which entry point is used.
_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
for _pkg in ("rag", "llm", "core"):
    logging.getLogger(_pkg).setLevel(_log_level)
logging.basicConfig(level=_log_level, format="%(levelname)s:%(name)s:%(message)s")

from typing import Any

import gradio as gr
from components.banner import build_banner
from core.schemas import CampaignSession, UserInfo
from pages.auth import build_auth_page
from pages.gm.campaigns import (
    CampaignPageRefs,
    build_campaigns_page,
    load_campaigns_for_user,
    resume_campaign,
)
from pages.gm.characters import build_characters_page
from pages.gm.history import build_gm_history_page
from pages.gm.npcs import build_npc_page
from pages.gm.players import build_players_page
from pages.gm.session_plan import build_session_plan_page
from pages.gm.knowledge_qa import build_knowledge_qa_page as build_gm_knowledge_qa_page
from pages.gm.rag_eval import build_rag_eval_page
from pages.gm.world_notes import build_world_notes_page
from pages.player.character import build_character_page
from pages.player.history import build_player_history_page
from pages.player.knowledge_qa import build_knowledge_qa_page as build_player_knowledge_qa_page
from pages.player.join import (
    build_player_join_page,
    load_joined_campaigns,
    on_join,
    on_row_select,
)
from pages.player.twin_chat import build_twin_chat_page
from services.db import get_backend


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
        with gr.Column(visible=True, elem_id="auth-column") as auth_col:
            build_auth_page(user_state)

        # ── Hub screen (post-login, before campaign selection) ────────────────
        with gr.Column(visible=False, elem_id="hub-column") as hub_col:
            with gr.Row(elem_id="hub-header-row"):
                gr.Markdown("## StoryWeaver", scale=4, elem_id="hub-header")
                hub_sign_out_btn = gr.Button(
                    "Sign Out",
                    scale=1,
                    size="sm",
                    elem_id="hub-signout-btn",
                )
            with gr.Tabs(elem_id="hub-tabs"):
                with gr.Tab("My Campaigns (GM)"):
                    campaign_refs: CampaignPageRefs = build_campaigns_page(
                        session_state, user_state
                    )
                with gr.Tab("Join a Campaign"):
                    player_join_refs = build_player_join_page(session_state, user_state)

        # ── Player dashboard ──────────────────────────────────────────────────
        with gr.Column(visible=False, elem_id="player-column") as player_col:
            with gr.Row(elem_id="player-header-row"):
                gr.Markdown(
                    "# StoryWeaver — Player Dashboard", scale=4, elem_id="player-header"
                )
                player_sign_out_btn = gr.Button(
                    "Sign Out",
                    scale=1,
                    size="sm",
                    elem_id="player-signout-btn",
                )
            with gr.Tabs(elem_id="player-tabs"):
                build_character_page(session_state)
                build_twin_chat_page(session_state)
                build_player_history_page(session_state)
                build_player_knowledge_qa_page(session_state)

        # ── GM dashboard ──────────────────────────────────────────────────────
        with gr.Column(visible=False, elem_id="gm-column") as gm_col:
            with gr.Row(elem_id="gm-header-row"):
                gr.Markdown(
                    "# StoryWeaver — GM Dashboard", scale=4, elem_id="gm-header"
                )
                gm_sign_out_btn = gr.Button(
                    "Sign Out",
                    scale=1,
                    size="sm",
                    elem_id="gm-signout-btn",
                )
            gm_join_code = gr.Textbox(
                label="Campaign Join Code — share this with your players",
                interactive=False,
                buttons=["copy"],
                elem_id="gm-join-code",
            )
            with gr.Tabs(elem_id="gm-tabs"):
                build_characters_page(session_state)
                build_npc_page(session_state)
                build_gm_history_page(session_state)
                build_world_notes_page(session_state)
                build_session_plan_page(session_state)
                build_players_page(session_state)
                build_gm_knowledge_qa_page(session_state)
                build_rag_eval_page(session_state)

        # ── Navigation ────────────────────────────────────────────────────────
        def _navigate(
            user: UserInfo | None, session: CampaignSession | None
        ) -> tuple[Any, ...]:
            """Return visibility updates for all panels + join code value.

            Output order must match _nav_outputs:
              auth_col, banner, hub_col, player_col, gm_col, gm_join_code
            """
            if user is None:
                return (
                    gr.update(visible=True, elem_id="auth-column"),
                    gr.update(visible=False, elem_id="banner"),
                    gr.update(visible=False, elem_id="hub-column"),
                    gr.update(visible=False, elem_id="player-column"),
                    gr.update(visible=False, elem_id="gm-column"),
                    gr.update(value="", elem_id="gm-join-code"),
                )
            if session is None:
                return (
                    gr.update(visible=False, elem_id="auth-column"),
                    gr.update(visible=False, elem_id="banner"),
                    gr.update(visible=True, elem_id="hub-column"),
                    gr.update(visible=False, elem_id="player-column"),
                    gr.update(visible=False, elem_id="gm-column"),
                    gr.update(value="", elem_id="gm-join-code"),
                )
            show_banner = not session.ai_available
            if session.role == "gm":
                return (
                    gr.update(visible=False, elem_id="auth-column"),
                    gr.update(visible=show_banner, elem_id="banner"),
                    gr.update(visible=False, elem_id="hub-column"),
                    gr.update(visible=False, elem_id="player-column"),
                    gr.update(visible=True, elem_id="gm-column"),
                    gr.update(value=session.join_code, elem_id="gm-join-code"),
                )
            return (
                gr.update(visible=False, elem_id="auth-column"),
                gr.update(visible=show_banner, elem_id="banner"),
                gr.update(visible=False, elem_id="hub-column"),
                gr.update(visible=True, elem_id="player-column"),
                gr.update(visible=False, elem_id="gm-column"),
                gr.update(value="", elem_id="gm-join-code"),
            )

        _nav_outputs = [
            auth_col,
            banner,
            hub_col,
            player_col,
            gm_col,
            gm_join_code,
        ]

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

        # ── Resume campaign — set session AND navigate in one event ───────────
        async def _on_resume(
            campaign_id_str: str | None, user: UserInfo | None
        ) -> tuple[Any, ...]:
            session = await resume_campaign(campaign_id_str, user)
            return (session,) + _navigate(user, session)

        campaign_refs.resume_btn.click(
            _on_resume,
            inputs=[campaign_refs.selected_campaign_id, user_state],
            outputs=[session_state] + _nav_outputs,
        )

        # ── Player join — set session AND navigate in one event ───────────────
        async def _on_player_join(
            code: str, user: UserInfo | None
        ) -> tuple[Any, ...]:
            message, session = await on_join(code, user)
            return (session, message) + _navigate(user, session)

        async def _on_player_rejoin(
            user: UserInfo | None, codes: list[str], evt: gr.SelectData
        ) -> tuple[Any, ...]:
            message, session = await on_row_select(user, codes, evt)
            return (session, message) + _navigate(user, session)

        _join_outputs = [session_state, player_join_refs.join_status] + _nav_outputs
        _rejoin_outputs = [session_state, player_join_refs.rejoin_status] + _nav_outputs

        player_join_refs.join_btn.click(
            _on_player_join,
            inputs=[player_join_refs.join_code_in, user_state],
            outputs=_join_outputs,
        )
        player_join_refs.join_code_in.submit(
            _on_player_join,
            inputs=[player_join_refs.join_code_in, user_state],
            outputs=_join_outputs,
        )
        player_join_refs.joined_table.select(
            _on_player_rejoin,
            inputs=[user_state, player_join_refs.joined_codes],
            outputs=_rejoin_outputs,
        )

        # ── Sign-out ──────────────────────────────────────────────────────────
        def _sign_out() -> tuple[None, None]:
            return None, None

        for _btn in (
            hub_sign_out_btn,
            gm_sign_out_btn,
            player_sign_out_btn,
        ):
            _btn.click(
                _sign_out,
                inputs=[],
                outputs=[user_state, session_state],
            )

        # Load campaigns whenever the user signs in (GM campaign list).
        user_state.change(
            load_campaigns_for_user,
            inputs=[user_state],
            outputs=[
                campaign_refs.table,
                campaign_refs.campaign_ids,
                campaign_refs.no_campaigns_msg,
            ],
        )

        # Load joined campaigns whenever the user signs in.
        user_state.change(
            load_joined_campaigns,
            inputs=[user_state],
            outputs=[player_join_refs.joined_table, player_join_refs.joined_codes],
        )

    return app


if __name__ == "__main__":
    import asyncio

    asyncio.run(_startup_verify())
    create_app().launch()
