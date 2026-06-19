"""Shared portrait and scene image display widget."""

from __future__ import annotations

import gradio as gr


def build_portrait_display(label: str = "Portrait") -> gr.Image:
    """Return a gr.Image component for portrait or scene illustration display."""
    return gr.Image(
        label=label,
        type="filepath",
        show_label=True,
        interactive=False,
        height=300,
        value=None,
    )
