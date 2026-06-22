# UI Contract: Knowledge Q&A

**Feature**: `005-rag-qa-system` | **Date**: 2026-06-22

---

## Overview

The Knowledge Q&A feature adds tabs to both the GM and Player dashboards. Both dashboards share a Q&A chat interface; the document upload and management panel differs by role:

| Role | Q&A Chat | PDF Upload | MD Upload | Doc List |
|---|---|---|---|---|
| GM | ✅ | ✅ | ✅ | ✅ (all docs) |
| Player | ✅ | ❌ | ✅ | ✅ (own uploads only) |

---

## 1. Gradio Tab: GM Dashboard — Knowledge Q&A

**Location**: `apps/web/pages/gm/knowledge_qa.py`
**Mounted in**: `apps/web/app.py` inside `gr.Tabs(elem_id="gm-tabs")`

### Layout

```
┌─ Tab: Knowledge Q&A ──────────────────────────────────────────────────┐
│                                                                        │
│  ┌─ Q&A Chat ─────────────────────────────────────────────────────┐   │
│  │  [Chatbot component — message history]                          │   │
│  │                                                                 │   │
│  │  [Source citations panel — shown below each assistant message]  │   │
│  │    • Doc Title — Section Headline (topic)                       │   │
│  │      > Excerpt text...                                          │   │
│  │                                                                 │   │
│  │  [User input textbox]          [Ask button]                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│  ┌─ Knowledge Base ───────────────────────────────────────────────┐   │
│  │  ┌── Upload ──────────────────────────────────────────────┐    │   │
│  │  │  File input (PDF or .md)                               │    │   │
│  │  │  Scope: [Global ▼] [Campaign-specific ▼]               │    │   │
│  │  │  Access default: [Player-visible ▼] [GM-only ▼] [Auto] │    │   │
│  │  │  [Upload & Ingest button]                              │    │   │
│  │  │  Upload status: [status message]                       │    │   │
│  │  └────────────────────────────────────────────────────────┘    │   │
│  │                                                                 │   │
│  │  ┌── Ingested Documents ──────────────────────────────────┐    │   │
│  │  │  Title | Format | Scope | Status | Chunks | Uploaded   │    │   │
│  │  │  ────────────────────────────────────────────────────  │    │   │
│  │  │  Earthdawn 4E Core | PDF | Global | ✅ ready | 342 | … │    │   │
│  │  │  Session 3 Notes   | MD  | Camp.  | ⏳ proc. | —   | … │    │   │
│  │  │  Blood Wood Lore   | MD  | Camp.  | ❌ failed | —  | … │    │   │
│  │  │                                                         │    │   │
│  │  │  [Refresh button]   (auto-refreshes every 5s via Timer) │    │   │
│  │  └────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### Gradio Components

| Component | `elem_id` | Type | Notes |
|---|---|---|---|
| Q&A chatbot | `gm-knowledge-chatbot` | `gr.Chatbot` | Message history; citations rendered as Markdown below each assistant turn |
| User input | `gm-knowledge-input` | `gr.Textbox` | `submit` fires ask handler; placeholder: "Ask about rules, lore, or world…" |
| Ask button | `gm-knowledge-ask-btn` | `gr.Button` | `variant="primary"` |
| File input | `gm-knowledge-file-upload` | `gr.File` | `file_types=[".pdf", ".md"]` |
| Scope dropdown | `gm-knowledge-scope` | `gr.Dropdown` | `choices=["Global (shared)", "Campaign-specific"]`; default `"Global (shared)"` for PDF, `"Campaign-specific"` for MD (auto-updated on file type change) |
| Access default | `gm-knowledge-access` | `gr.Dropdown` | `choices=["Auto (LLM infers)", "Player-visible", "GM-only"]`; default `"Auto (LLM infers)"` |
| Upload button | `gm-knowledge-upload-btn` | `gr.Button` | Disabled until a file is selected |
| Upload status | `gm-knowledge-upload-status` | `gr.Markdown` | Shows upload confirmation, duplicate warning with confirm/cancel, or error |
| Confirm overwrite | `gm-knowledge-confirm-overwrite` | `gr.Button` | Hidden by default; shown only when duplicate detected |
| Cancel overwrite | `gm-knowledge-cancel-overwrite` | `gr.Button` | Hidden by default |
| Doc table | `gm-knowledge-doc-table` | `gr.Dataframe` | Columns: Title, Format, Scope, Status, Chunks, Uploaded; read-only |
| Refresh button | `gm-knowledge-refresh-btn` | `gr.Button` | Manual refresh; `gr.Timer` also auto-refreshes |
| Status timer | — | `gr.Timer(value=5)` | Fires every 5s to poll ingestion status |

### Event Handlers

| Event | Handler | Inputs | Outputs |
|---|---|---|---|
| `ask_btn.click` / `input.submit` | `on_ask` | `[session_state, chatbot, input]` | `[chatbot, input]` |
| `upload_btn.click` | `on_upload` | `[session_state, file, scope, access_default]` | `[upload_status, confirm_btn (visible), cancel_btn (visible)]` |
| `confirm_overwrite_btn.click` | `on_confirm_overwrite` | `[session_state, file, scope, access_default]` | `[upload_status, confirm_btn (hidden), cancel_btn (hidden)]` |
| `cancel_overwrite_btn.click` | `on_cancel_overwrite` | `[]` | `[upload_status, confirm_btn (hidden), cancel_btn (hidden)]` |
| `refresh_btn.click` / `timer.tick` | `on_refresh_docs` | `[session_state]` | `[doc_table]` |
| `session_state.change` | `on_session_change` | `[session_state]` | `[chatbot, doc_table]` (clear on session change) |

---

## 2. Gradio Tab: Player Dashboard — Knowledge Q&A

**Location**: `apps/web/pages/player/knowledge_qa.py`
**Mounted in**: `apps/web/app.py` inside `gr.Tabs(elem_id="player-tabs")`

### Layout

```
┌─ Tab: Knowledge Q&A ──────────────────────────────────────────────────┐
│                                                                        │
│  ┌─ Q&A Chat ─────────────────────────────────────────────────────┐   │
│  │  [Chatbot — player-visible content only]                        │   │
│  │  [Source citations panel]                                       │   │
│  │  [User input]                          [Ask button]             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│  ┌─ My Contributions ─────────────────────────────────────────────┐   │
│  │  File input (.md only)                                          │   │
│  │  Access: [Player-visible ▼] [GM-only ▼] (default: player)      │   │
│  │  [Upload button]                                                │   │
│  │  Status: [status message]                                       │   │
│  │                                                                 │   │
│  │  My uploaded files:                                             │   │
│  │  Title | Status | Chunks | Uploaded                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### Gradio Components

| Component | `elem_id` | Type | Notes |
|---|---|---|---|
| Chatbot | `player-knowledge-chatbot` | `gr.Chatbot` | Same citation rendering as GM tab |
| User input | `player-knowledge-input` | `gr.Textbox` | Same placeholder as GM tab |
| Ask button | `player-knowledge-ask-btn` | `gr.Button` | `variant="primary"` |
| File input | `player-knowledge-file-upload` | `gr.File` | `file_types=[".md"]` only |
| Access dropdown | `player-knowledge-access` | `gr.Dropdown` | `choices=["Player-visible", "GM-only"]`; default `"Player-visible"` |
| Upload button | `player-knowledge-upload-btn` | `gr.Button` | Disabled until file selected |
| Upload status | `player-knowledge-upload-status` | `gr.Markdown` | Confirmation, duplicate warning, or error |
| Confirm overwrite | `player-knowledge-confirm-overwrite` | `gr.Button` | Hidden by default |
| Cancel overwrite | `player-knowledge-cancel-overwrite` | `gr.Button` | Hidden by default |
| Doc table | `player-knowledge-doc-table` | `gr.Dataframe` | Shows only documents uploaded by this player |
| Timer | — | `gr.Timer(value=5)` | Polls ingestion status |

---

## 3. Citation Rendering Format

Citations are rendered as Markdown within the chatbot `assistant` message. Each cited chunk is displayed as a collapsible-style block immediately following the answer text:

```markdown
**Sources:**

> **[Doc Title] — [Headline]** *(topic label)*
> Excerpt text from the chunk, up to ~200 characters, ending with "…" if truncated.

> **[Doc Title] — [Headline]** *(topic label)*
> Excerpt text…
```

Citations are ordered by RRF score (highest first). Maximum 5 citations shown per answer.

---

## 4. Error and Empty States

| Condition | Display |
|---|---|
| Knowledge base empty | Chatbot shows: "No documents have been ingested yet. Ask your GM to upload rulebooks or lore files." |
| LLM unavailable | Chatbot shows: "The knowledge service is unavailable — check that Ollama is running and try again." |
| No relevant content found | Chatbot shows: "I couldn't find relevant information for your question in the current knowledge base." |
| Ingestion failed | Doc table row shows ❌ with error message visible on hover or in a status row |
| Stale processing (>15 min) | Doc table row shows ⚠️ "Ingestion stalled — restart may be required." |
| Player attempts PDF upload | Upload button disabled; file input restricted to `.md` files via `file_types` |

---

## 5. Service Layer Contract (`apps/web/services/knowledge.py`)

The page modules call these service functions:

```python
async def ask_question(
    question: str,
    campaign_id: uuid.UUID,
    role: str,                        # "gm" | "player"
) -> tuple[str, list[KnowledgeChunk]]:
    """Return (answer_text, ranked_cited_chunks). Raises ProviderUnavailableError."""

async def submit_document(
    file_path: str,
    filename: str,
    title: str,
    scope: str,                       # "global" | "campaign"
    campaign_id: uuid.UUID | None,
    access_level_default: str | None, # "gm_only" | "player_visible" | None
    format: str,                      # "pdf" | "markdown"
) -> KnowledgeDocument:
    """Register the document and fire background ingestion task."""

async def check_duplicate(
    title: str,
    scope: str,
    campaign_id: uuid.UUID | None,
) -> KnowledgeDocument | None:
    """Return existing document if a duplicate exists, else None."""

async def confirm_overwrite(
    doc_id: uuid.UUID,
    file_path: str,
) -> None:
    """Replace existing document: delete chunks, reset status, re-ingest."""

async def list_documents(
    campaign_id: uuid.UUID,
    scope_filter: str | None = None,   # None = both global + campaign
) -> list[KnowledgeDocument]:
    """Return documents visible to this campaign, ordered by created_at desc."""
```