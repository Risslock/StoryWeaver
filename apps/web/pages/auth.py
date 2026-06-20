"""Sign-in / Create Account panel — shown when no user session exists."""

from __future__ import annotations

import gradio as gr
from core.schemas import UserInfo
from services.auth import register_user, validate_user
from services.db import get_backend
from storage.users import get_user_by_username_or_email


def build_auth_page(user_state: gr.State) -> None:
    """Render login and registration tabs inside the current Blocks context."""
    gr.Markdown("# StoryWeaver")
    gr.Markdown("Your AI-powered tabletop RPG companion.")

    with gr.Tabs():
        with gr.TabItem("Sign In"):
            login_id = gr.Textbox(
                label="Username or Email", placeholder="adventurer42"
            )
            login_pw = gr.Textbox(label="Password", type="password")
            login_btn = gr.Button("Sign In", variant="primary")
            login_status = gr.Markdown("")

            async def on_login(
                identifier: str, password: str
            ) -> tuple[UserInfo | None, str]:
                identifier = identifier.strip()
                if not identifier or not password:
                    return None, "Enter your username and password."
                backend = get_backend()
                ok = await validate_user(backend, identifier, password)
                if not ok:
                    return None, "Invalid username or password."
                async with await backend.get_session() as session:
                    user = await get_user_by_username_or_email(session, identifier)
                    if user is None:
                        return None, "Invalid username or password."
                    return UserInfo(user_id=user.id, username=user.username), ""

            login_btn.click(
                on_login,
                inputs=[login_id, login_pw],
                outputs=[user_state, login_status],
            )

        with gr.TabItem("Create Account"):
            reg_username = gr.Textbox(
                label="Username", placeholder="adventurer42", max_lines=1
            )
            reg_email = gr.Textbox(
                label="Email", placeholder="you@example.com"
            )
            reg_pw = gr.Textbox(label="Password", type="password")
            reg_confirm = gr.Textbox(label="Confirm Password", type="password")
            reg_btn = gr.Button("Create Account", variant="primary")
            reg_status = gr.Markdown("")

            async def on_register(
                username: str,
                email: str,
                password: str,
                confirm: str,
            ) -> tuple[UserInfo | None, str]:
                if password != confirm:
                    return None, "Passwords do not match."
                backend = get_backend()
                ok, msg = await register_user(backend, username, email, password)
                if not ok:
                    return None, msg
                async with await backend.get_session() as session:
                    user = await get_user_by_username_or_email(
                        session, username.strip()
                    )
                    if user is None:
                        return None, "Account created — please sign in."
                    return (
                        UserInfo(user_id=user.id, username=user.username),
                        "✓ Account created!",
                    )

            reg_btn.click(
                on_register,
                inputs=[reg_username, reg_email, reg_pw, reg_confirm],
                outputs=[user_state, reg_status],
            )
