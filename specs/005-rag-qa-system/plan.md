# Implementation Plan: Game Knowledge Q&A (RAG)

**Branch**: `005-rag-qa-system` | **Date**: 2026-06-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-rag-qa-system/spec.md`

## Summary

A two-tier RAG knowledge base that lets GMs and players ask natural-language questions about game rules, lore, and world content — and receive synthesized answers citing the exact source passages. A shared `knowledge_global` ChromaDB collection holds rulebooks and sourcebooks indexed once for all campaigns; a per-campaign collection holds campaign-specific notes and lore. GMs ingest PDF rulebooks (converted to Markdown with table preservation and inline image descriptions) or Markdown notes; players contribute Markdown files. The pipeline enriches every chunk with LLM-generated metadata (headline, summary, topic, access level) validated via Pydantic models; access levels are inferred per-chunk by the LLM with a document-level default override set at upload time. Retrieval uses multi-query expansion (3 alternative phrasings) and Reciprocal Rank Fusion (RRF) across both collections. Embeddings use `nomic-embed-text` via Ollama through ChromaDB's `OllamaEmbeddingFunction`. The Gradio UI provides a Q&A chat pane on both dashboards, plus upload/management (GM: PDF + MD; player: MD only), with real-time ingestion status via DB polling.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:
- `chromadb>=0.4` — vector store (already in `packages/rag/pyproject.toml`)
- `pymupdf4llm` — PDF → Markdown conversion with table extraction and image byte extraction (Apache 2.0); **new, add to `packages/rag/pyproject.toml`**
- `pydantic-ai` — structured Pydantic model validation of LLM outputs (`ChunkEnrichment`, `QueryExpansion`); already a workspace dependency, **add to `packages/rag/pyproject.toml`**
- `storyweaver-llm` — text generation for enrichment, query expansion, and answer synthesis (existing abstraction)
- `gradio>=4.0` — UI (existing)
- `storyweaver-core` — ORM models, SQLite backend

**Storage**:
- SQLite (existing) — new `knowledge_documents` table for document registry and ingestion status
- ChromaDB persistent store at `./data/chroma` — two-tier collections:
  - `knowledge_global` — shared rulebooks/sourcebooks, indexed once for all campaigns
  - `knowledge_{campaign_id_hex}` — campaign-specific notes and lore
- Both collections created with `OllamaEmbeddingFunction(model_name="nomic-embed-text", url=OLLAMA_BASE_URL)` — **not** ChromaDB's default `all-MiniLM-L6-v2` embedding. Existing `RulesRetriever` and `CharacterRetriever` use the ChromaDB default; the knowledge collections use Ollama embeddings via a separate collection configuration. The two embedding spaces are not mixed.

**Testing**: pytest + pytest-asyncio (existing); harness evals in `harness/knowledge_qa/`

**Target Platform**: Local desktop (same as existing app — no new deployment requirements)

**Performance Goals**:
- Q&A answer with citations: ≤30 seconds end-to-end (SC-001)
- PDF ingestion fully queryable: ≤10 minutes for typical 200-page rulebook (SC-002)
- Markdown ingestion fully queryable: ≤2 minutes (SC-003)

**Constraints**:
- No FastAPI or separate backend service (constitution Principle VI)
- Local-only by default; vector store and LLM provider swappable via env var (Principle II, IV)
- No new auth stack; role determined from `CampaignSession.role` (existing mock auth)
- IP compliance: chunks and inline captions only; raw original content not redistributed
- Background ingestion via `asyncio.create_task`; status polled from SQLite via `gr.Timer`

**Scale/Scope**: Two-tier retrieval (global + campaign); MVP targets ≥3 documents total, up to ~500-page PDFs. Global rulebooks shared across all campaigns with no re-ingestion cost.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Spec-Driven | ✅ Pass | Spec + clarifications complete in `specs/005-rag-qa-system/` |
| II. Provider Abstraction | ✅ Pass | `KnowledgeRetriever` and `Ingestor` behind ABCs; vector store and LLM swappable via env var |
| III. Package Isolation | ✅ Pass | New `knowledge/` sub-module inside existing `packages/rag/`; no unjustified new top-level package |
| IV. Local-First | ✅ Pass | ChromaDB local persistent; Ollama LLM; no mandatory cloud path |
| V. Harness-Driven Quality | ✅ Pass | Harness evals required before milestone; see quickstart.md |
| VI. Product-First | ✅ Pass | No new auth; mock session role for access filter; Gradio-only |
| VII. Placeholder-First | ✅ Pass | Both new tabs render visible placeholder before real logic is wired |
| IP Compliance | ✅ Pass | Chunks + LLM-generated captions stored; originals not redistributed |

## PDF Content Extraction Strategy

Rulebook PDFs contain three content types that require distinct handling:

### Tables (stat blocks, talent circles, attribute progressions)
- `pymupdf4llm` converts tables to GitHub-flavored Markdown table syntax automatically.
- The chunker treats tables as **atomic units** — a table is never split across chunk boundaries.
- A heading immediately preceding a table is included in the same chunk (heading + table = one chunk).
- Very large standalone tables get their own dedicated chunk with an LLM-generated headline.

### Images (maps, character art, diagrams, rule illustrations)
- `pymupdf4llm` extracts image bytes per page. The `PdfIngestor` accepts an optional `image_captioner: Callable[[bytes], str] | None` parameter.
- When provided, the callable is invoked per image to produce a short description; the description is **inserted as a Markdown paragraph at the image's position** before chunking — no image files are stored.
- When `None` (default), the system emits `[Figure: page {p}, image {n}]` — always visible, never silent (Principle VII).
- The existing `LLMProvider` interface (`packages/llm/llm/interface.py`) only accepts `str` prompts and has no multi-modal path. Rather than extend the interface now, the image captioner is injected as a plain async callable at construction time. A concrete Ollama vision helper function can be added to `packages/llm/` in a future spec when multi-modal models are validated. For MVP, the placeholder fallback is sufficient.
- This keeps the module lightweight: images produce searchable text, no filesystem I/O beyond the PDF itself.

### Plain Text and Headings
- Heading-based splitting: each `##` / `###` section boundary triggers a new candidate chunk.
- Chunks are bounded by a configurable max token length (default 800 tokens); oversized sections split at paragraph breaks.
- ~50-token overlap between adjacent chunks preserves cross-boundary context.

## Structured Output Pattern

LLM calls that must return structured data (chunk enrichment, query expansion) use the following pattern to avoid fragile text parsing:

1. The `LLMProvider.generate()` call uses a prompt that instructs the model to respond with valid JSON matching a defined schema.
2. The response string is parsed with `Model.model_validate_json(raw)` (Pydantic v2).
3. On `ValidationError`, the call is retried once with a corrective prompt. If it fails again, a safe fallback is used (e.g. `access_level="player_visible"`, empty `summary`).

This approach reuses the existing `LLMProvider` abstraction (Principle II) while benefiting from Pydantic's validation and type-safety. The `pydantic-ai` dependency is added to `packages/rag/pyproject.toml` to provide the Pydantic models used as result schemas (`ChunkEnrichment`, `QueryExpansion`).

**Models** (defined in `packages/rag/rag/knowledge/interface.py`):

```python
class ChunkEnrichment(BaseModel):
    headline: str                                    # ≤80 chars
    summary: str                                     # 1–2 sentences
    topic: str                                       # e.g. "combat/initiative"
    access_level: Literal["gm_only", "player_visible"]

class QueryExpansion(BaseModel):
    alternatives: list[str]                          # exactly 3 items
```

## Project Structure

### Documentation (this feature)

```text
specs/005-rag-qa-system/
├── plan.md              # This file
├── research.md          # Phase 0 — technology decisions
├── data-model.md        # Phase 1 — entities and DB schema
├── quickstart.md        # Phase 1 — validation guide
├── contracts/
│   └── knowledge-qa-ui.md   # Phase 1 — UI contract
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
packages/rag/
├── pyproject.toml                   # add pymupdf4llm and pydantic-ai dependencies
└── rag/
    └── knowledge/
        ├── __init__.py
        ├── interface.py             # KnowledgeRetriever ABC, KnowledgeChunk dataclass
        ├── enricher.py              # LLM chunk enrichment (headline/summary/topic/access_level)
        ├── chunker.py               # Heading-based MD splitter, table-atomic + image inline
        ├── ingestor.py              # Ingestor ABC + PdfIngestor + MarkdownIngestor
        ├── pipeline.py              # Orchestrator: convert → chunk → enrich → index
        └── retriever.py             # ChromaDB KnowledgeRetriever with RRF + access filter

packages/core/
└── core/
    ├── models.py                    # Add KnowledgeDocument ORM model
    └── migrations/versions/
        └── 0005_knowledge_documents.py

apps/web/
├── pages/
│   ├── gm/
│   │   └── knowledge_qa.py          # GM tab: Q&A chat + PDF & MD upload + status list
│   └── player/
│       └── knowledge_qa.py          # Player tab: Q&A chat + MD upload only
├── services/
│   └── knowledge.py                 # Bridge: background ingest dispatch, status queries
└── app.py                           # Wire new tabs into GM and player Tabs

harness/
└── knowledge_qa/
    ├── test_ingestion.py             # Eval: ingest produces expected chunk count and metadata
    ├── test_retrieval.py             # Eval: Q&A accuracy, RRF ranking, access filter enforcement
    └── fixtures/
        ├── sample_rules.md           # Plain rules text for ingestion tests
        └── sample_gm_only.md         # GM-only content for access-filter tests
```

## Complexity Tracking

No constitution violations. Adding `knowledge/` as a sub-module of `packages/rag/` is justified because it shares the existing `Retriever` ABC and ChromaDB dependency already declared in `packages/rag/pyproject.toml`. No new top-level package is introduced.