# Data Model: Game Knowledge Q&A (RAG)

**Feature**: `005-rag-qa-system` | **Date**: 2026-06-22

---

## Overview

This feature introduces one new SQLite ORM entity (`KnowledgeDocument`) and a two-tier ChromaDB vector store topology. All existing entities are unchanged.

---

## 1. SQLite: KnowledgeDocument

Tracks every document submitted to the knowledge pipeline — its ingestion status, scope, and access defaults. ChromaDB holds the actual chunk vectors; this table is the authoritative registry.

### ORM Model (addition to `packages/core/core/models.py`)

```python
class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("scope", "campaign_id", "title", name="uq_knowledge_doc_title"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # "global" = shared rulebook; "campaign" = campaign-scoped note/lore
    scope: Mapped[str] = mapped_column(String(16), nullable=False)

    # NULL when scope="global"; required when scope="campaign"
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False)      # "pdf" | "markdown"

    # Document-level access default set by the uploader at upload time.
    # NULL = no override; each chunk keeps its LLM-inferred access level.
    access_level_default: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # "pending" | "processing" | "ready" | "failed"
    ingestion_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    campaign: Mapped[Campaign | None] = relationship("Campaign")
```

### Constraints

| Constraint | Rule |
|---|---|
| Uniqueness | `(scope, campaign_id, title)` — title unique per scope+campaign. For global docs, `campaign_id=NULL` and all global docs share the same uniqueness space. |
| `scope` | Must be `"global"` or `"campaign"` |
| `format` | Must be `"pdf"` or `"markdown"` |
| `access_level_default` | Must be `"gm_only"`, `"player_visible"`, or `NULL` |
| `ingestion_status` | Must be `"pending"`, `"processing"`, `"ready"`, or `"failed"` |
| `campaign_id` | Required when `scope="campaign"`; must be NULL when `scope="global"` |

### State Transitions

```
[upload submitted]
      ↓
   pending
      ↓  (pipeline starts)
  processing
      ↓                  ↓
   ready               failed  (error_message set)
      ↓  (confirmed overwrite uploaded)
  processing  (recycled)
```

Stale detection: if `ingestion_status="processing"` and `updated_at` is >15 minutes ago, the UI shows a warning and offers a manual re-trigger.

---

## 2. ChromaDB: Vector Collections

ChromaDB is not managed by Alembic. Collections are created lazily on first use by `KnowledgeRetriever`.

### Collection Naming

| Collection | Purpose |
|---|---|
| `knowledge_global` | Shared rulebooks and sourcebooks — indexed once, queried from all campaigns |
| `knowledge_{campaign_id_hex}` | Campaign-scoped content (notes, lore, GM secrets) |

### Chunk Document Schema

Each chunk stored in ChromaDB uses the following structure:

| Field | Type | Description |
|---|---|---|
| `id` | `string` | `{doc_id_hex}_{chunk_index:04d}` — globally unique, deterministic |
| `document` | `string` | Full chunk text (raw content + inline image captions) |
| `metadata.doc_id` | `string` | UUID of the `KnowledgeDocument` row |
| `metadata.doc_title` | `string` | Human-readable document title |
| `metadata.chunk_index` | `int` | Zero-based position within the document |
| `metadata.headline` | `string` | LLM-generated heading for this chunk |
| `metadata.summary` | `string` | LLM-generated 1–2 sentence summary |
| `metadata.topic` | `string` | LLM-generated topic label (e.g., "combat", "talents", "lore/blood-wood") |
| `metadata.access_level` | `string` | `"gm_only"` or `"player_visible"` (effective after override) |
| `metadata.scope` | `string` | `"global"` or `"campaign"` |
| `metadata.campaign_id` | `string` \| `null` | Campaign UUID hex, or null for global chunks |

### Access-Level Filter

- **Player query**: `where={"access_level": {"$eq": "player_visible"}}` — applied to both collections.
- **GM query**: no filter — all chunks visible.

---

## 3. Pydantic Models (in `packages/rag/rag/knowledge/`)

### ChunkEnrichment — pydantic-ai `result_type` for the enricher agent

```python
from typing import Literal
from pydantic import BaseModel

class ChunkEnrichment(BaseModel):
    headline: str           # Short title for this chunk (≤80 chars)
    summary: str            # 1–2 sentence summary
    topic: str              # Topic label (e.g. "combat/initiative", "lore/blood-wood")
    access_level: Literal["gm_only", "player_visible"]
```

### QueryExpansion — pydantic-ai `result_type` for the query expansion agent

```python
class QueryExpansion(BaseModel):
    alternatives: list[str]   # 3 alternative phrasings of the original query
```

### KnowledgeChunk — returned from the retriever to the answer generator

```python
@dataclass
class KnowledgeChunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    headline: str
    summary: str
    topic: str
    access_level: str
    scope: str
    text: str
    rrf_score: float          # Final RRF score after multi-query merge
```

---

## 4. Alembic Migration

**File**: `packages/core/core/migrations/versions/0005_knowledge_documents.py`

Creates the `knowledge_documents` table with:
- All columns as defined above
- `uq_knowledge_doc_title` unique constraint
- Index on `campaign_id`
- Index on `ingestion_status` (for stale detection polling)

No existing table is modified.