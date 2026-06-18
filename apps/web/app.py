"""Gradio app factory for StoryWeaver."""

from __future__ import annotations

import gradio as gr
from components.banner import build_banner
from core.schemas import CampaignSession
from pages.gm.characters import build_characters_page
from pages.gm.npcs import build_npc_page
from pages.gm.world_notes import build_world_notes_page
from pages.landing import build_landing
from pages.player.character import build_character_page
from pages.player.twin_chat import build_twin_chat_page


def create_app() -> gr.Blocks:
    with gr.Blocks(title="StoryWeaver") as app:
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
                with gr.Tab("Story History"):
                    gr.Markdown("*Story history coming in Phase 5.*")

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
                with gr.Tab("Story History"):
                    gr.Markdown("*Story history coming in Phase 5.*")
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
    app = create_app()
    app.launch(theme=gr.themes.Soft())