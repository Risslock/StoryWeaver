# Research: RAG Evaluation Tab & Q&A Source Visibility

## Retriever Interface (confirmed from codebase)

**Decision**: Use `ChromaKnowledgeRetriever.search()` directly for evaluation retrieval.

**Rationale**: `ask_question()` in `services/knowledge.py` already uses this retriever.
Evaluation MUST use the same code path (FR-011) — no separate retrieval implementation.

**Key facts**:
- `ChromaKnowledgeRetriever.search(query, campaign_id, role, top_k)` returns `list[KnowledgeChunk]`
- `KnowledgeChunk.text` holds the chunk's full text (use this instead of `page_content`)
- Default `top_k=8` via env `KNOWLEDGE_TOP_K`; evaluation will override with the GM-chosen k
- Role `"gm"` applies no access filter — GMs see all chunks (good for unbiased evaluation)
- The retriever does multi-query expansion + RRF internally; evaluation measures the final
  ranked list that the Q&A system actually uses

---

## Metric Calculations

### MRR (Mean Reciprocal Rank)

**Decision**: Compute per-keyword, then average across all keywords for a question.

```
RR(keyword) = 1/rank_of_first_chunk_containing_keyword  (0 if not found)
MRR(question) = mean(RR(kw) for kw in question.keywords)
```

Case-insensitive substring match: `keyword.lower() in chunk.text.lower()`

**Rationale**: Same approach as provided `eval.py`. Measures how early the relevant content
appears in the ranked list — crucial for generation quality since LLMs weight early context.

### nDCG (Normalized Discounted Cumulative Gain)

**Decision**: Binary relevance (1/0) per chunk per keyword, average across keywords.

```
rel(i, kw) = 1 if kw.lower() in chunk[i].text.lower() else 0
DCG(kw) = sum(rel(i, kw) / log2(i+2) for i in 0..k-1)
IDCG(kw) = DCG of ideal ranking (all rel=1 chunks first)
nDCG(kw) = DCG(kw) / IDCG(kw)   (0.0 if IDCG=0)
nDCG(question) = mean(nDCG(kw) for kw in question.keywords)
```

**Rationale**: Discounts relevance by rank — a match at rank 1 is worth more than at rank 10.
Complements MRR: MRR rewards first-hit position; nDCG rewards density across the full list.

### Recall@k

**Decision**: Fraction of keywords found in any of the top-k chunks.

```
Recall@k(question) = |{kw : kw found in any of chunks[0..k-1]}| / |keywords|
```

**Rationale**: Simpler than MRR/nDCG — did the system retrieve *all* the relevant facts
at all? A high Recall@k with low MRR means the information is there but buried.

---

## GM Role Access (confirmed)

**Decision**: No new access-control code needed.

**Rationale**: Gradio's navigation state machine in `app.py` shows the `gm_col` (GM dashboard,
with all GM tabs) only when `session_state.role == "gm"`. Adding the Evaluation tab to
`gm_col` automatically restricts it to GMs. Players never see `gm_col`.

`CampaignSession.role` is set to `"gm"` or `"player"` at campaign join/resume time in
existing service code. No new model or field required.

---

## Q&A Sources Separation

**Decision**: Keep `gr.Chatbot` for conversation turns; add a separate `gr.Accordion`
below containing a `gr.Markdown` sources panel, closed by default.

**Rationale**: `gr.Chatbot` only renders the last assistant message format — it cannot
easily split inline text into separate components after render. The cleanest separation is:
- `on_ask()` returns answer text (without citations) → chatbot
- `on_ask()` also returns formatted citations markdown → sources markdown component
- Sources component lives inside a `gr.Accordion("Show sources", open=False)`
- Chatbot entry clears citation suffix appended in current code (lines 202–209 of `knowledge_qa.py`)

Sources markdown is overwritten on each new answer; opening the accordion shows the
citations for the most recent answer only (acceptable for Q&A chat UX).

---

## Evaluation JSONL Schema

**Decision**: Adopt the `TestQuestion` schema from the provided `test.py` verbatim.

```json
{
  "question": "What is the maximum Strain a character can take per action?",
  "keywords": ["Strain", "maximum", "action"],
  "reference_answer": "A character can take up to their Toughness in Strain per action.",
  "category": "direct_fact"
}
```

Fields: `question` (str), `keywords` (list[str]), `reference_answer` (str), `category` (str).

**Rationale**: User will prepare the JSONL file; keeping the exact same schema minimises
the learning curve and the `reference_answer` field is present for future LLM-judge extension.

---

## Source Code Layout

**New files**:
```
packages/rag/rag/knowledge/evaluator.py       # Pure metric functions (MRR, nDCG, Recall@k)
packages/rag/rag/knowledge/test_questions.py  # TestQuestion Pydantic model + JSONL loader
apps/web/services/eval.py                     # Async evaluation service (bridges UI ↔ RAG)
apps/web/pages/gm/rag_eval.py                # Gradio RAG Evaluation tab
```

**Modified files**:
```
apps/web/pages/gm/knowledge_qa.py             # Separate answer from sources in Q&A chat
apps/web/app.py                               # Register rag_eval tab in gm_col
```

---

## Alternatives Considered

| Topic | Alternative | Rejected Because |
|-------|-------------|-----------------|
| Metric location | Compute metrics in `services/eval.py` | Metrics are pure math with no I/O; belong in the RAG package where they're independently testable |
| Sources display | Inline in chatbot message with collapsible HTML | Gradio's `gr.Chatbot` does not support interactive components inside messages |
| JSONL loading | Server-side file path input (text box) | Gradio file-upload component is safer and works cross-platform without filesystem path assumptions |
| k adjustment | Fixed at 10 | Users explicitly asked for adjustable k |
