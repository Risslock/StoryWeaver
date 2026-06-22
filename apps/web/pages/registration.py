"""Unauthenticated registration companion app — mounted at /register."""

from __future__ import annotations

import gradio as gr
from services.auth import register_user
from services.db import get_backend


def create_registration_app() -> gr.Blocks:
    with gr.Blocks(title="StoryWeaver — Create Account") as app:
        gr.Markdown("# StoryWeaver — Create Account")

        username_in = gr.Textbox(
            label="Username", max_lines=1, placeholder="adventurer42"
        )
        email_in = gr.Textbox(label="Email", placeholder="you@example.com")
        password_in = gr.Textbox(label="Password", type="password")
        confirm_in = gr.Textbox(label="Confirm Password", type="password")

        submit_btn = gr.Button("Create Account", variant="primary")
        status_out = gr.Markdown("")

        gr.Markdown("Already have an account? [Sign in](/).")

        async def on_submit(
            username: str,
            email: str,
            password: str,
            confirm: str,
        ) -> str:
            if password != confirm:
                return "Passwords do not match."
            backend = get_backend()
            ok, msg = await register_user(backend, username, email, password)
            if ok:
                return "✓ Account created! [Sign in here](/) to get started."
            return msg

        submit_btn.click(
            on_submit,
            inputs=[username_in, email_in, password_in, confirm_in],
            outputs=[status_out],
        )

    return app
