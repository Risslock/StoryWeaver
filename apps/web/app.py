"""Gradio app factory for StoryWeaver.

Multi-user session isolation model
───────────────────────────────────
1. Per-tab state: gr.State(value=None) holds a CampaignSession dataclass.
   Gradio 4.x guarantees that gr.State is isolated per browser tab — no
   CampaignSession object is ever shared between concurrent user sessions.

2. No module-level mutable session state: CampaignSession is never stored in a
   module-level variable. All state flows through gr.State and event handlers.

3. Concurrent DB writes: SQLiteBackend sets PRAGMA journal_mode=WAL at
   connection-open time (packages/storage/sqlite/adapter.py). WAL allows
   concurrent readers alongside a single serialised writer, preventing
   read-blocking and database locking under multi-user load.
"""

from __future__ import annotations

import gradio as gr

from components.banner import build_banner
from core.schemas import CampaignSession
from pages.gm.characters import build_characters_page
from pages.gm.history import build_gm_history_page
from pages.gm.npcs import build_npc_page
from pages.gm.world_notes import build_world_notes_page
from pages.landing import build_landing, get_backend
from pages.player.character import build_character_page
from pages.player.history import build_player_history_page
from pages.player.twin_chat import build_twin_chat_page


async def _startup_verify() -> None:
    """Initialize the DB and verify WAL mode is active before serving requests."""
    db = get_backend()
    await db.initialize_db()
    if not await db.verify_wal_mode():
        raise RuntimeError(
            "SQLite WAL mode is not active. "
            "Concurrent reads and writes may block each other. "
            "Ensure the database URL points to a file-based SQLite database."
        )


def create_app() -> gr.Blocks:
    with gr.Blocks(title="StoryWeaver") as app:
        # gr.State is per-browser-tab in Gradio 4.x — CampaignSession never leaks
        # between concurrent user connections.
        session_state: gr.State = gr.State(value=None)

        banner = build_banner()

        # ── Landing ───────────────────────────────────────────────────────
        with gr.Column(visible=True) as landing_col:
            build_landing(session_state)

        # ── Player dashboard ──────────────────────────────────────────────
        with gr.Column(visible=False) as player_col:
            gr.Markdown("# StoryWeaver — Player Dashboard")
            with gr.Tabs():
                build_character_page(session_state)
                build_twin_chat_page(session_state)
                build_player_history_page(session_state)

        # ── GM dashboard ──────────────────────────────────────────────────
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
                with gr.Tab("Session Plan"):
                    gr.Markdown("*Session planning coming in Phase 8.*")

        # ── Navigation triggered by session_state changes ────────────────
        def _navigate(state: CampaignSession | None) -> tuple:
            """Show the correct panel and conditionally display the AI banner."""
            if state is None:
                return (
                    gr.update(visible=True),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(value=""),
                )
            show_banner = not state.ai_available
            if state.role == "gm":
                return (
                    gr.update(visible=False),
                    gr.update(visible=show_banner),
                    gr.update(visible=False),
                    gr.update(visible=True),
                    gr.update(value=state.join_code),
                )
            return (
                gr.update(visible=False),
                gr.update(visible=show_banner),
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(value=""),
            )

        session_state.change(
            _navigate,
            inputs=[session_state],
            outputs=[landing_col, banner, player_col, gm_col, gm_join_code],
        )

    return app


if __name__ == "__main__":
    import asyncio

    asyncio.run(_startup_verify())
    app = create_app()
    app.launch(theme=gr.themes.Soft())