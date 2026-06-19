"""ComfyUI local image generation provider."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import aiofiles
import httpx
from core.config import settings
from core.errors import ProviderUnavailableError

from imagegen.interface import ImageGenRequest, ImageGenResponse, ImageProvider

_DEFAULT_WORKFLOW: dict = {
    "3": {
        "inputs": {
            "seed": 0,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
            "model": ["4", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
        "class_type": "KSampler",
    },
    "4": {
        "inputs": {"ckpt_name": "v1-5-pruned-emaonly.ckpt"},
        "class_type": "CheckpointLoaderSimple",
    },
    "5": {
        "inputs": {"width": 512, "height": 512, "batch_size": 1},
        "class_type": "EmptyLatentImage",
    },
    "6": {
        "inputs": {"text": "", "clip": ["4", 1]},
        "class_type": "CLIPTextEncode",
    },
    "7": {
        "inputs": {"text": "", "clip": ["4", 1]},
        "class_type": "CLIPTextEncode",
    },
    "8": {
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        "class_type": "VAEDecode",
    },
    "9": {
        "inputs": {"filename_prefix": "storyweaver", "images": ["8", 0]},
        "class_type": "SaveImage",
    },
}

_POLL_INTERVAL = 2.0
_MAX_POLLS = 60


class ComfyUIProvider(ImageProvider):
    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.comfyui_url).rstrip("/")

    async def generate(self, request: ImageGenRequest) -> ImageGenResponse:
        workflow = json.loads(json.dumps(_DEFAULT_WORKFLOW))
        workflow["6"]["inputs"]["text"] = request.prompt
        workflow["7"]["inputs"]["text"] = request.negative_prompt
        workflow["5"]["inputs"]["width"] = request.width
        workflow["5"]["inputs"]["height"] = request.height
        workflow["3"]["inputs"]["seed"] = int(uuid.uuid4().int % (2**32))

        client_id = str(uuid.uuid4())
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._base_url}/prompt",
                    json={"prompt": workflow, "client_id": client_id},
                )
                resp.raise_for_status()
                prompt_id = resp.json()["prompt_id"]
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(f"Cannot reach ComfyUI at {self._base_url}") from exc
        except (httpx.HTTPStatusError, KeyError) as exc:
            return ImageGenResponse(error=f"ComfyUI submission failed: {exc}")

        for _ in range(_MAX_POLLS):
            await asyncio.sleep(_POLL_INTERVAL)
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    history = (
                        await client.get(f"{self._base_url}/history/{prompt_id}")
                    ).json()
            except Exception as exc:
                return ImageGenResponse(error=f"ComfyUI polling error: {exc}")

            if prompt_id not in history:
                continue

            for node_output in history[prompt_id].get("outputs", {}).values():
                images = node_output.get("images", [])
                if not images:
                    continue
                img_meta = images[0]
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        dl = await client.get(
                            f"{self._base_url}/view",
                            params={
                                "filename": img_meta["filename"],
                                "subfolder": img_meta.get("subfolder", ""),
                                "type": img_meta.get("type", "output"),
                            },
                        )
                        dl.raise_for_status()
                except Exception as exc:
                    return ImageGenResponse(error=f"Failed to download image from ComfyUI: {exc}")

                images_dir = Path(settings.images_dir)
                images_dir.mkdir(parents=True, exist_ok=True)
                file_path = images_dir / f"{request.entity_id}.png"
                async with aiofiles.open(file_path, "wb") as f:
                    await f.write(dl.content)
                return ImageGenResponse(image_url=str(file_path))

        return ImageGenResponse(error="ComfyUI generation timed out after 2 minutes.")
