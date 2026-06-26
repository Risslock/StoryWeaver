# Contract: IngestionConfig & IngestionPipeline.run()

**Modules**: `packages/rag/rag/knowledge/interface.py`, `packages/rag/rag/knowledge/pipeline.py`

---

## IngestionConfig (new, in interface.py)

```python
@dataclass
class IngestionConfig:
    """All preprocessing options for a single ingestion run.

    Add new ingestion-time options here — never as extra kwargs on pipeline.run().
    """
    source_type: Literal["rulebook", "supplement", "handwritten_note", "novel"] = "rulebook"
    access_level_default: str | None = None       # overrides LLM-assigned access_level per chunk
    enable_breadcrumbs: bool = True               # prepend structural heading path to each chunk
    enable_contextual_summaries: bool = False     # generate LLM situating summary per chunk
    cleaning: bool = True                         # run CorpusCleaner on extracted text
```

**Why a dataclass and not kwargs**: The ingestion pipeline is accumulating preprocessing options (source_type, cleaning, access_level_default, and now breadcrumbs + contextual summaries). Without a dedicated config object, every new option would grow the `run()` signature. `IngestionConfig` is the single place to look for all ingestion-time knobs. Callers pass a config object; the pipeline unpacks it internally.

**Default behaviour** (`IngestionConfig()` with no arguments):
- Source type: `"rulebook"`
- Access level: LLM-assigned per chunk
- Breadcrumbs: enabled
- Contextual summaries: disabled (opt-in due to per-chunk LLM cost)
- Cleaning: enabled

---

## Updated IngestionPipeline.run()

```python
async def run(
    self,
    doc_id: str,
    file_path: str,
    format: str,                        # "pdf" or "md"
    scope: str,                         # "global" or campaign UUID string
    campaign_id: str | None,
    config: IngestionConfig = IngestionConfig(),
) -> None:
```

**Removed from the top-level signature** (moved into `IngestionConfig`):
- `access_level_default` — was a top-level param; now `config.access_level_default`
- `source_type` — was a top-level param; now `config.source_type`

**The only production caller** is `apps/web/services/knowledge.py:_run_pipeline()`, which must be updated to construct an `IngestionConfig` and pass it.

---

## ChromaDB Metadata Written per Chunk

```python
{
    "doc_id": str,
    "doc_title": str,
    "chunk_index": int,
    "headline": str,
    "summary": str,
    "topic": str,
    "access_level": str,       # "gm_only" | "player_visible"
    "scope": str,
    "campaign_id": str,
    "original_text": str,      # breadcrumb + "\n\n" + raw_text (when enable_breadcrumbs=True)
    "breadcrumb": str,         # NEW — structural path alone; "" when no heading found
    "source_type": str,        # NEW — always written; value from config.source_type
}
```

---

## Compound Text Assembly

`_build_records` assembles the compound text from available parts:

| Flag state | Compound text order |
|-----------|-------------------|
| breadcrumbs off, summaries off | `headline \n\n summary \n\n raw_text` (unchanged) |
| breadcrumbs on, summaries off | `breadcrumb \n\n headline \n\n summary \n\n raw_text` |
| breadcrumbs on, summaries on | `breadcrumb \n\n contextual_summary \n\n headline \n\n summary \n\n raw_text` |

`original_text` metadata field stores `breadcrumb + "\n\n" + raw_text` when breadcrumbs are enabled, so `KnowledgeChunk.text` always includes the breadcrumb for display purposes.

---

## Ingestor Extension

`Ingestor` ABC gains a new method used by the pipeline:

```python
async def extract_with_context(
    self,
    file_path: str,
    config: IngestionConfig,
) -> tuple[str, list[str]]:
    """Return (full_cleaned_markdown_text, chunks).

    The full text is needed by BreadcrumbExtractor to scan heading positions.
    Existing ingest() and ingest_async() remain for tests and external callers.
    """
```

Both `PdfIngestor` and `MarkdownIngestor` implement `extract_with_context`. The existing sync `ingest()` method used in `test_ingestion.py` is unchanged.

---

## Error Behaviour

| Failure | Behaviour |
|---------|-----------|
| Contextual summary LLM call fails (any exception) | Chunk ingested without summary; WARNING logged with breadcrumb and failure reason; run continues |
| Breadcrumb extraction finds no headings | Empty string breadcrumb; no exception; chunk stored with `breadcrumb=""` |
| Breadcrumb extractor cannot locate a chunk in the Markdown | Falls back to last-known heading; empty string if none found |
| `ProviderUnavailableError` during enrichment | Run marked `failed` in SQLite (existing behaviour, unchanged) |
