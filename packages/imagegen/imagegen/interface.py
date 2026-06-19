"""ImageProvider ABC and data contracts for image generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from pydantic import BaseModel

# Fixed prefix prepended to every portrait prompt to enforce a consistent
# painterly fantasy style across all characters and NPCs.
PORTRAIT_PROMPT_PREFIX = (
    "fantasy character portrait, Earthdawn setting, painterly illustration, "
    "rich jewel-tone colors, dramatic rim lighting, detailed face and costume, "
    "high quality digital art"
)

# Elements to suppress in every portrait generation.
PORTRAIT_NEGATIVE_PROMPT = (
    "blurry, deformed, bad anatomy, extra limbs, ugly, watermark, "
    "signature, text, poorly drawn, low quality, photorealistic"
)


class ImageGenRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    style_hints: list[str] = []
    width: int = 512
    height: int = 512
    entity_id: UUID


class ImageGenResponse(BaseModel):
    image_url: str | None = None
    error: str | None = None


class ImageProvider(ABC):
    @abstractmethod
    async def generate(self, request: ImageGenRequest) -> ImageGenResponse:
        """Generate an image. Returns response with image_url or error — never raises."""