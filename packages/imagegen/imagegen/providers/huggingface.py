"""HuggingFace Inference API image provider.

Default free-tier model: black-forest-labs/FLUX.1-schnell
Other free options: stabilityai/stable-diffusion-xl-base-1.0, runwayml/stable-diffusion-v1-5
"""

from __future__ import annotations

from pathlib import Path

import aiofiles
import httpx

from core.config import settings
from imagegen.interface import ImageGenRequest, ImageGenResponse, ImageProvider

_HF_API_BASE = "https://router.huggingface.co/hf-inference/models"


class HuggingFaceProvider(ImageProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.hf_api_key
        self._model = model or settings.hf_image_model

    async def generate(self, request: ImageGenRequest) -> ImageGenResponse:
        if not self._api_key:
            return ImageGenResponse(
                error="HF_API_KEY is not set. Get a free token at https://huggingface.co/settings/tokens"
            )

        prompt = request.prompt
        if request.style_hints:
            prompt = prompt + ", " + ", ".join(request.style_hints)

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{_HF_API_BASE}/{self._model}",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "inputs": prompt,
                        "parameters": {
                            "width": request.width,
                            "height": request.height,
                            **(
                                {"negative_prompt": request.negative_prompt}
                                if request.negative_prompt
                                else {}
                            ),
                        },
                    },
                )
        except httpx.ConnectError:
            return ImageGenResponse(
                error="Cannot reach HuggingFace Inference API. "
                "Check your network connection."
            )
        except httpx.TimeoutException:
            return ImageGenResponse(error="Image generation timed out after 120s.")

        if response.status_code == 503:
            return ImageGenResponse(
                error="Model is still loading on HuggingFace servers. Please try again in a moment."
            )
        if response.status_code == 401:
            return ImageGenResponse(error="Invalid HuggingFace API key.")
        if response.status_code == 429:
            return ImageGenResponse(error="HuggingFace rate limit exceeded. Try again later.")
        if not response.is_success:
            return ImageGenResponse(error=f"HuggingFace API error {response.status_code}: {response.text[:200]}")

        images_dir = Path(settings.images_dir)
        images_dir.mkdir(parents=True, exist_ok=True)
        file_path = images_dir / f"{request.entity_id}.png"

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(response.content)

        return ImageGenResponse(image_url=str(file_path))
