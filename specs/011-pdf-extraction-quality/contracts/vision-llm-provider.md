# Contract: VisionLLMProvider

**Package**: `packages/llm/llm/interface.py`
**Status**: New (feature 011)

---

## Purpose

Defines the provider-agnostic interface for converting a rendered PDF page image into structured Markdown text. This abstraction allows switching between local vision models (Ollama multimodal) and future providers (OpenAI Vision, Claude Vision) via environment-variable configuration only — no code changes required (Constitution II).

---

## Abstract Base Class

```python
from abc import ABC, abstractmethod

class VisionLLMProvider(ABC):
    @abstractmethod
    async def extract_page(self, image_bytes: bytes, prompt: str) -> str:
        """
        Convert a rendered page image to Markdown text.

        Args:
            image_bytes: Raw PNG bytes of the rendered page.
            prompt: Extraction instruction sent to the model.

        Returns:
            Markdown text extracted from the page. May be empty string if
            the model produces no output. NEVER returns None.

        Raises:
            RuntimeError: If the provider call fails (network error, timeout,
                          non-2xx HTTP response, or malformed response JSON).
                          Callers are responsible for fallback handling.
        """
```

---

## Concrete Implementation: OllamaVisionProvider

**File**: `packages/llm/llm/providers/ollama.py`

### Construction

```python
OllamaVisionProvider(
    model: str,                    # e.g. "minicpm-v", "llava", "moondream2"
    base_url: str = "http://localhost:11434",
    timeout_secs: int = 120,
)
```

All three values are read from environment variables in the factory function:

| Env Var | Used For |
|---------|---------|
| `KNOWLEDGE_VISION_MODEL` | `model` parameter |
| `OLLAMA_BASE_URL` | `base_url` parameter |
| `KNOWLEDGE_VISION_TIMEOUT_SECS` | `timeout_secs` parameter |

### API Call

**Endpoint**: `POST {base_url}/api/generate`

**Request payload**:
```json
{
  "model": "<model>",
  "prompt": "<prompt>",
  "images": ["<base64-encoded PNG string>"],
  "stream": false
}
```

**Success response** (HTTP 200):
```json
{
  "response": "## Chapter Title\n\n...",
  "done": true
}
```
Returns `response_json["response"]`.

**Error conditions**:

| Condition | Behaviour |
|-----------|-----------|
| HTTP status != 200 | Raise `RuntimeError(f"Vision model returned {status}: {body[:200]}")` |
| Request timeout | Raise `RuntimeError(f"Vision model timed out after {timeout_secs}s")` |
| `response` field missing | Return `""` (treated same as empty response; caller retries) |
| `response` is empty string | Return `""` (caller retries up to KNOWLEDGE_VISION_MAX_RETRIES times) |

### Logging

All log calls use the module-level logger `_log = logging.getLogger(__name__)`.

| Event | Level | Message pattern |
|-------|-------|----------------|
| Successful extraction | DEBUG | `"Vision extracted page in %.1fs (%.0f chars)"` |
| HTTP error | ERROR | `"Vision model HTTP %d for page render"` |
| Timeout | WARNING | `"Vision model timed out after %ds"` |

---

## Usage Pattern (pipeline side)

```python
# In IngestionPipeline._extract() when config.extraction_mode == "vision":
vision_model = os.getenv("KNOWLEDGE_VISION_MODEL")
if not vision_model:
    raise IngestionAbortError(
        "KNOWLEDGE_VISION_MODEL env var is required for extraction_mode='vision' but is not set"
    )

timeout_secs = int(os.getenv("KNOWLEDGE_VISION_TIMEOUT_SECS", "120"))
provider = OllamaVisionProvider(model=vision_model, timeout_secs=timeout_secs)
ingestor = VisionPdfIngestor(vision_provider=provider)
return await ingestor.extract(file_path, config)
```

> **Note**: The `KNOWLEDGE_VISION_MODEL` guard lives in `IngestionPipeline._extract()` (pipeline.py), not inside `VisionPdfIngestor`. This keeps the ingestor pure — it only accepts an already-configured provider.

---

## Retry & Abort Contract

`VisionPdfIngestor` calls `extract_page()` per page. If `extract_page()` raises `RuntimeError` **or** returns an empty string after stripping:

1. Retry up to `KNOWLEDGE_VISION_MAX_RETRIES` additional times (env var, default 1; total attempts = retries + 1)
2. Log each retry at `WARNING` level: `"Vision extraction failed for page %d (attempt %d/%d): %s — retrying"`
3. If all retries are exhausted: log `ERROR: "Vision extraction aborted after %d attempts on page %d: %s"` and raise `IngestionAbortError` (or equivalent) to stop the pipeline

**There is no fallback to pymupdf4llm text extraction**. Vision mode runs fully committed — partial chunks already written to ChromaDB are left in place and will be overwritten by the next successful ingestion run.

**Model not configured**: If `KNOWLEDGE_VISION_MODEL` is unset when `extraction_mode="vision"` is requested, `VisionPdfIngestor` raises `IngestionAbortError` immediately before rendering any pages, with message: `"KNOWLEDGE_VISION_MODEL env var is required for extraction_mode='vision' but is not set"`.
