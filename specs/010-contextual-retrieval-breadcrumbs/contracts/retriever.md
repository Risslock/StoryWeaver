# Contract: KnowledgeChunk & KnowledgeRetriever

**Module**: `packages/rag/rag/knowledge/interface.py` and `retriever.py`

---

## KnowledgeChunk (updated)

```python
@dataclass
class KnowledgeChunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    headline: str
    summary: str
    topic: str
    access_level: str        # "gm_only" | "player_visible"
    scope: str               # "global" | campaign UUID
    text: str                # original_text from ChromaDB; includes breadcrumb prefix when ingested with enable_breadcrumbs=True
    rrf_score: float
    breadcrumb: str = ""          # NEW: structural location path; "" for chunks ingested before feature 010
    source_type: str = "rulebook" # NEW: document classification; "rulebook" default for pre-010 chunks
```

**`text` field note**: When chunks were ingested with `enable_breadcrumbs=True`, `text` starts with the breadcrumb prefix (`"{breadcrumb}\n\n{raw_text}"`). When ingested without breadcrumbs, `text` is the raw chunk text as before. The `breadcrumb` field always contains the breadcrumb string alone for structured access.

## KnowledgeRetriever.search() (unchanged signature)

```python
async def search(
    self,
    query: str,
    campaign_id: str,
    role: str,
    top_k: int = 8,
) -> list[KnowledgeChunk]:
```

No `source_type` filter parameter is added. Source-type awareness is handled in the LLM/prompt layer at chat time.

## ChromaKnowledgeRetriever changes

The retriever reads two new metadata fields from ChromaDB results and populates them into `KnowledgeChunk`:

```python
KnowledgeChunk(
    ...existing fields...,
    breadcrumb=str(meta.get("breadcrumb", "")),
    source_type=str(meta.get("source_type", "rulebook")),
)
```

No changes to the `where` clause construction or query logic.
