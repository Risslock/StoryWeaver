"""Gradio app factory for StoryWeaver."""

from __future__ import annotations

import gradio as gr

from components.banner import build_banner
from core.schemas import CampaignSession
from pages.landing import build_landing


def create_app() -> gr.Blocks:
    with gr.Blocks(title="StoryWeaver") as app:
        session_state: gr.State = gr.State(value=None)

        banner = build_banner()

        with gr.Row(visible=True) as landing_row:
            build_landing(session_state)

        with gr.Row(visible=False) as player_row:
            gr.Markdown("## Player Dashboard\n\n*(Phase 3 implementation pending)*")

        with gr.Row(visible=False) as gm_row:
            gr.Markdown("## GM Dashboard\n\n*(Phase 3–4 implementation pending)*")

        def on_session_change(state: CampaignSession | None) -> tuple[dict, dict, dict, dict]:
            if state is None:
                return (
                    gr.update(visible=True),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False),
                )
            ai_banner_visible = not state.ai_available
            if state.role == "gm":
                return (
                    gr.update(visible=False),
                    gr.update(visible=ai_banner_visible),
                    gr.update(visible=False),
                    gr.update(visible=True),
                )
            return (
                gr.update(visible=False),
                gr.update(visible=ai_banner_visible),
                gr.update(visible=True),
                gr.update(visible=False),
            )

        session_state.change(
            on_session_change,
            inputs=[session_state],
            outputs=[landing_row, banner, player_row, gm_row],
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.launch()