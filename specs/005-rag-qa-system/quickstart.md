# Quickstart & Validation Guide: Game Knowledge Q&A (RAG)

**Feature**: `005-rag-qa-system` | **Date**: 2026-06-22

This guide covers how to validate the feature end-to-end after implementation. It is not a tutorial; for implementation details see [data-model.md](data-model.md) and [contracts/knowledge-qa-ui.md](contracts/knowledge-qa-ui.md).

---

## Prerequisites

### 1. Ollama Models

Two Ollama models are required — one for LLM inference/enrichment, one for embeddings:

```bash
# Text generation model (for enrichment, query expansion, answer synthesis)
ollama pull llama3.1

# Embedding model — REQUIRED for chunk indexing and retrieval
ollama pull nomic-embed-text
```

Verify both are available:
```bash
ollama list
# Expected output includes both:
#   llama3.1       ...
#   nomic-embed-text   ...
```

If `nomic-embed-text` is missing, ingestion will fail with a `ProviderUnavailableError` during the embedding step. The UI must show a user-visible error message, not a blank panel.

### 2. Database Migration

```bash
uv run alembic upgrade head
# Should output: Running upgrade ... -> 0005_knowledge_documents, add knowledge_documents table
```

### 3. App Launch

```bash
uv run python apps/web/main.py
```

### 4. Accounts and Campaign

- At least one GM user and one Player user created
- A campaign created by the GM
- Player account joined the campaign

---

## Validation Scenarios

### Scenario 1 — Placeholder Tab Visible Before Ingestion (Principle VII)

**Goal**: Confirm both tabs render immediately before any content is ingested.

1. Sign in as GM and open a campaign → navigate to **Knowledge Q&A** tab.
2. **Expected**: Tab renders with chatbot showing "No documents have been ingested yet" and an upload panel.
3. Sign in as Player, join the campaign → navigate to **Knowledge Q&A** tab.
4. **Expected**: Tab renders with the same empty-state message and an MD-only upload panel.

---

### Scenario 2 — Markdown Ingestion (GM, Campaign Scope)

**Goal**: Ingest a Markdown file as GM and confirm it becomes queryable.

1. Create `test_lore.md`:
   ```markdown
   ## The Blood Wood
   The Blood Wood is the home of the Elves of Barsaive. After the Scourge, the elves
   chose to remain in their forest rather than retreat to kaers. To survive, they
   merged with their trees using blood magic, creating the horrific Blood Elves.
   The forest is now twisted and covered in thorns.
   ```
2. As GM, go to **Knowledge Q&A → Knowledge Base → Upload**.
3. Select `test_lore.md`, scope **Campaign-specific**, access **Player-visible**. Click **Upload & Ingest**.
4. **Expected**: Status shows ⏳ processing; document appears in the table.
5. Wait ≤2 minutes. **Expected**: Status changes to ✅ ready, chunk count ≥ 1.
6. In the chatbot: "What happened to the elves during the Scourge?"
7. **Expected**: Answer mentions blood magic or Blood Wood; at least one citation shows `test_lore.md — The Blood Wood`.

---

### Scenario 3 — Global Scope Accessible from All Campaigns

**Goal**: Confirm a globally-scoped document is queryable from a different campaign without re-uploading.

1. Upload `test_lore.md` again with scope **Global (shared)**. Wait for ✅ ready.
2. Open (or create) a **different campaign**. Ask the same Blood Wood question.
3. **Expected**: Answer cites `test_lore.md`; the global document is available without re-upload.

---

### Scenario 4 — Access Level Filtering (GM-Only Content Hidden from Players)

**Goal**: Confirm GM-only chunks never surface to players.

1. Create `secret_plot.md`:
   ```markdown
   ## Secret Plot
   The cult leader is actually Kaer Volsk's own council elder. This is GM-only information.
   ```
2. As GM, upload with scope **Campaign-specific**, access **GM-only**. Wait for ✅ ready.
3. As GM, ask: "Who is the cult leader?" → **Expected**: Answer references the council elder; citation shows `secret_plot.md`.
4. Sign in as Player in the same campaign. Ask the same question.
5. **Expected**: "I couldn't find relevant information for your question in the current knowledge base." — zero citations.

---

### Scenario 5 — Duplicate Document Warning and Overwrite

**Goal**: Confirm the system warns and requires confirmation before replacing a document.

1. As GM, attempt to upload `test_lore.md` when it already exists (from Scenario 2 or 3).
2. **Expected**: Status shows "⚠️ A document named 'test_lore' already exists. Confirm overwrite?" with Confirm and Cancel buttons.
3. Click **Cancel**. **Expected**: Upload aborted, original document unchanged in the table.
4. Upload again and click **Confirm**. **Expected**: Document resets to ⏳ processing, re-ingests, returns to ✅ ready.

---

### Scenario 6 — Player Cannot Upload PDF

**Goal**: Confirm the Player upload input accepts only `.md` files.

1. Sign in as Player → **Knowledge Q&A → My Contributions**.
2. Attempt to select a `.pdf` file.
3. **Expected**: File picker rejects non-`.md` files (Gradio `file_types=[".md"]`); no upload occurs.

---

### Scenario 7 — LLM/Embedding Unavailable Error Handling

**Goal**: Confirm graceful visible error when Ollama is unreachable.

1. Stop Ollama or set `OLLAMA_BASE_URL` to an unreachable address.
2. Sign in as GM → **Knowledge Q&A** → ask any question.
3. **Expected**: Chatbot shows "The knowledge service is unavailable — check that Ollama is running and try again." No crash, no blank panel.
4. Attempt to upload and ingest a file.
5. **Expected**: Document status changes to ❌ failed with a visible error message.

---

### Scenario 8 — Multi-Document Synthesis

**Goal**: Confirm answers synthesize across multiple documents.

1. Ingest a second file `test_rules.md` describing combat:
   ```markdown
   ## Combat Initiative
   At the start of combat, all participants roll Initiative using their DEX step.
   The character with the highest result acts first.
   ```
2. Ask: "How do initiative and the Blood Wood affect gameplay?"
3. **Expected**: Answer draws from both `test_lore.md` and `test_rules.md`; both documents appear in citations.

---

## Harness Evaluation Targets

These evals must pass before the milestone is considered complete (constitution Principle V):

| Eval | File | Pass Criterion |
|---|---|---|
| MD ingest produces enriched chunks | `harness/knowledge_qa/test_ingestion.py` | `chunk_count >= 1`; each chunk has non-empty `headline`, `summary`, `topic`, valid `access_level` |
| Embedding model check | `harness/knowledge_qa/test_ingestion.py` | Fails with `ProviderUnavailableError` (not silent) when `nomic-embed-text` is not available |
| GM-only filter blocks player | `harness/knowledge_qa/test_retrieval.py` | Player query returns 0 chunks for GM-only content |
| RRF ranking relevance | `harness/knowledge_qa/test_retrieval.py` | Directly relevant chunk appears in top-3 for a targeted question |
| No hallucination on empty KB | `harness/knowledge_qa/test_retrieval.py` | Answer contains "couldn't find" phrase; 0 citations returned |
| Stale processing detection | `harness/knowledge_qa/test_ingestion.py` | Document with `updated_at` >15 min and status `processing` triggers visible warning |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | LLM and embedding provider endpoint (existing) |
| `KNOWLEDGE_EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model used for chunk and query embedding |
| `KNOWLEDGE_LLM_MODEL` | `llama3.1` | Ollama model used for enrichment, query expansion, and answer synthesis |
| `KNOWLEDGE_MAX_CHUNK_TOKENS` | `800` | Max tokens per chunk before splitting |
| `KNOWLEDGE_CHUNK_OVERLAP_TOKENS` | `50` | Overlap between adjacent chunks |
| `KNOWLEDGE_TOP_K` | `8` | Chunks retrieved per sub-query before RRF |
| `KNOWLEDGE_RRF_K` | `60` | RRF rank constant |
| `KNOWLEDGE_EXPANSION_COUNT` | `3` | Number of alternative query phrasings to generate |
| `KNOWLEDGE_ENRICH_MODEL` | `llama3.2` | Ollama model used for chunk enrichment (fast, small model — separate from the answer synthesis model) |
| `KNOWLEDGE_ENRICH_BATCH_SIZE` | `5` | Number of chunks sent to the enrichment LLM in a single call. Reduce if local Ollama runs out of context; increase if using a model with a large context window. |