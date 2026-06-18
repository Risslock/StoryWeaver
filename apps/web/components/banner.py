"""AI-unavailable degraded-mode banner component."""

from __future__ import annotations

import gradio as gr


_BANNER_HTML = (
    '<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:6px;'
    'padding:12px 16px;margin-bottom:12px;color:#856404;font-weight:500;">'
    "⚠️ AI features are currently unavailable. "
    "Character sheets, story history, and campaign navigation remain accessible."
    "</div>"
)


def build_banner() -> gr.HTML:
    """Return a persistent banner shown when ai_available is False."""
    return gr.HTML(value=_BANNER_HTML, visible=False, elem_id="ai-unavailable-banner")