"""Provider factory — selects ImageProvider based on IMAGE_PROVIDER env var."""

from __future__ import annotations

from core.config import settings
from imagegen.interface import ImageProvider


def get_image_provider() -> ImageProvider:
    if settings.image_provider == "huggingface":
        from imagegen.providers.huggingface import HuggingFaceProvider
        return HuggingFaceProvider()
    if settings.image_provider == "comfyui":
        from imagegen.providers.comfyui import ComfyUIProvider
        return ComfyUIProvider()
    raise ValueError(f"Unknown image provider: {settings.image_provider!r}")