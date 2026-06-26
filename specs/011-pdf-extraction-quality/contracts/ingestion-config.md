# Contract: IngestionConfig (updated)

**Package**: `packages/rag/rag/knowledge/interface.py`
**Status**: Modified (feature 011 adds `extraction_mode` field)

---

## Purpose

`IngestionConfig` is the single configuration object passed to `IngestionPipeline.run()` for every document ingestion. Feature 011 adds one new field — `extraction_mode` — to select between text-layer extraction (existing) and vision LLM extraction (new).

---

## Full Field Reference

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class IngestionConfig:
    # --- Existing fields (feature 010, unchanged) ---
    source_type: str = "pdf"
    access_level_default: str = "public"
    enable_breadcrumbs: bool = True
    enable_contextual_summaries: bool = True
    cleaning: CleaningConfig = field(default_factory=CleaningConfig)

    # --- New field (feature 011) ---
    extraction_mode: Literal["text", "vision"] = "text"
```

---

## extraction_mode Semantics

| Value | Behaviour |
|-------|-----------|
| `"text"` (default) | Uses `PdfIngestor` → `pymupdf4llm.to_markdown()`. Identical to pre-011 behaviour. No new dependencies or model calls. |
| `"vision"` | Uses `VisionPdfIngestor` → renders pages via PyMuPDF + calls `OllamaVisionProvider.extract_page()` per page. Falls back to text extraction per page on failure. Requires `KNOWLEDGE_VISION_MODEL` env var to be set. |

**Backward compatibility**: All existing call sites that construct `IngestionConfig` without the `extraction_mode` field receive the default `"text"`, which is identical to the pre-011 behaviour. No migration required.

---

## Validation Rules

- `extraction_mode` must be one of `"text"` or `"vision"`. Any other value raises `ValueError` at pipeline entry.
- When `extraction_mode="vision"` and `KNOWLEDGE_VISION_MODEL` is not set: the pipeline logs `WARNING` and silently downgrades to `"text"` for the entire document. No exception is raised.

---

## Effect on ChromaDB Metadata

Every chunk stored in ChromaDB gains the metadata key `"extraction_mode"` set to the value of `config.extraction_mode` (or `"text"` if a per-page fallback occurred). This enables benchmark comparison by extraction strategy.

---

## Related Environment Variables

| Variable | Required for | Default |
|----------|-------------|---------|
| `KNOWLEDGE_VISION_MODEL` | `extraction_mode="vision"` | *(none — falls back to text if missing)* |
| `KNOWLEDGE_VISION_TIMEOUT_SECS` | `extraction_mode="vision"` | `120` |
| `KNOWLEDGE_MIN_CHUNK_CHARS` | Post-chunk quality gate | `150` |
| `KNOWLEDGE_MAX_CHUNK_CHARS` | Post-chunk quality gate | `15000` |
