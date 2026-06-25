# Contract: LLMProvider Structured Output

**Feature**: `008-corpus-cleaning` (Decision 10)
**Modules**: `packages/llm/llm/interface.py`, `packages/llm/llm/providers/ollama.py`
**Date**: 2026-06-25

---

## Purpose

Extend the `LLMProvider` abstraction with a typed structured output method so callers can
receive a parsed Pydantic model instead of a raw string. `OllamaProvider` overrides the
default to enable `response_format: json_object` on the Ollama OpenAI-compat endpoint,
eliminating the three JSON parse failure modes observed in `AgenticChunker`.

---

## Method Signature

```python
from typing import TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

async def generate_structured(
    self,
    prompt: str,
    response_type: type[T],
    system: str = "",
) -> T:
    ...
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | `str` | User-role message sent to the model |
| `response_type` | `type[T]` where `T: BaseModel` | Pydantic model class that defines the expected JSON schema |
| `system` | `str` | Optional system prompt (default: empty string) |

### Return value

An instance of `response_type` populated from the model's JSON response. Field presence,
types, and constraints are validated by Pydantic.

### Exceptions raised

| Exception | Condition |
|-----------|-----------|
| `pydantic.ValidationError` | Model returned valid JSON but it does not conform to `response_type`'s schema (wrong field names, wrong types, missing required fields) |
| `ProviderUnavailableError` | Underlying HTTP call failed (same as `generate()`) |

**Does NOT raise** `json.JSONDecodeError` when `OllamaProvider` is in use — `json_object` mode
prevents syntactically invalid JSON at the sampler level.

---

## Provider Implementations

### `LLMProvider` (base class — default fallback)

```python
async def generate_structured(self, prompt, response_type, system=""):
    raw = await self.generate(prompt=prompt, system=system)
    return response_type.model_validate_json(raw)
```

Calls `generate()` and parses. `json.JSONDecodeError` is NOT caught here — callers
must handle it. All current providers (`AnthropicProvider`, `OpenAIProvider`,
`HuggingFaceProvider`) inherit this default and gain the typed interface without changes.

### `OllamaProvider` (override — JSON mode)

```python
async def generate_structured(self, prompt, response_type, system=""):
    payload = {
        "model": self._model,
        "messages": [...],
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    # ... httpx POST to /v1/chat/completions ...
    return response_type.model_validate_json(raw)
```

The `response_format: {"type": "json_object"}` field instructs Ollama's sampler to produce
syntactically valid JSON. Supported since Ollama v0.1.14 on the `/v1/chat/completions` endpoint.

**Future upgrade path**: replace `{"type": "json_object"}` with:
```python
{
    "type": "json_schema",
    "json_schema": {
        "name": response_type.__name__,
        "schema": response_type.model_json_schema(),
    }
}
```
This constrains the model to the exact Pydantic schema (field names + types), not just valid
JSON. Requires Ollama v0.5+. No caller changes needed — the method signature is identical.

---

## Caller Contract (`AgenticChunker._chunk_batch`)

```python
from pydantic import ValidationError

try:
    result = await llm.generate_structured(
        prompt=prompt,
        response_type=_ChunkBoundaryResponse,
        system=_SYSTEM_PROMPT,
    )
except ValidationError as exc:
    _log.debug(
        "Structured response did not match schema (sections=%d): %s — one chunk per section",
        len(sections), exc,
    )
    return list(sections)

boundary_set = {(e.section, e.start_sentence) for e in result.chunks}
```

**Callers MUST catch `ValidationError`** — it replaces the former `json.JSONDecodeError` catch.
`ProviderUnavailableError` should propagate to the pipeline for user-visible handling (unchanged).

---

## Logging Contract

| Scenario | Level | Message |
|----------|-------|---------|
| Model returns `{"chunks": []}` | *(none)* | Parsed successfully; no log |
| `ValidationError` (schema mismatch) | `DEBUG` | `"Structured response did not match schema (sections=N): ... — one chunk per section"` |
| `ProviderUnavailableError` | — | Propagates; logged by the pipeline, not the chunker |

The former WARNING `"Failed to parse LLM batch response"` is eliminated. `DEBUG` is correct
because a fallback to one-chunk-per-section for a short section is expected and benign behaviour.

---

## Invariants

- `generate_structured()` never returns `None`.
- If `response_type` has no required fields and the model returns `{}`, Pydantic parses it
  successfully with default values (if any). Callers should define required fields with no
  defaults for fields that must be present.
- `generate_structured()` does NOT modify the prompt to add JSON format instructions.
  The existing prompt already requests JSON; `response_format` enforces it at the sampler level.
  Adding redundant format instructions to the prompt is not needed and should be avoided.
