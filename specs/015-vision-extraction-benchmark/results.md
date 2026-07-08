# Results: Vision Extraction Benchmark (feature 015)

Running lab notebook for the benchmark. Filled in as each phase completes (tasks.md).

## T001 — Environment verification (2026-07-07)

Ollama reachable at `http://localhost:11434`. Models pulled (relevant subset):

| Role | Model | Pulled? |
|---|---|---|
| Vision extraction | `blaifa/Nanonets-OCR-s:latest` | ✅ |
| Embedding | `nomic-embed-text:latest` | ✅ |
| Enrich | `llama3.1:latest` | ✅ |
| Answer LLM | `llama3.1:latest` | ✅ |
| Judge (`JUDGE_MODEL`) | `llama3.1` (via `JUDGE_PROVIDER=ollama`) | ✅ |

Corpus source PDF located at `C:\Users\juane\Documents\Juanes\Hobbies\Rol\Earthdawn\ED4_Players_Guide.pdf` (not tracked in the repo — operator-local path).

Existing `knowledge_documents` row for the corpus: `id=bf5af91681744f16842fda4f583a18a0`, `scope=global`, `title=ED4_Players_Guide`, `format=pdf`, `ingestion_status=ready`, `chunk_count=780` (current production state — this is the collection that will be clean-slated and re-ingested twice by this benchmark).

## T002 — Held-fixed config snapshot (2026-07-07)

Captured from `.env` at benchmark start — these MUST be identical across the Docling and Vision legs (FR-009):

```
KNOWLEDGE_CHUNKING_STRATEGY=agentic
KNOWLEDGE_MAX_CHUNK_TOKENS=2500
KNOWLEDGE_CHUNK_OVERLAP_TOKENS=200
KNOWLEDGE_MIN_CHUNK_CHARS=300
KNOWLEDGE_MAX_CHUNK_CHARS=15000
KNOWLEDGE_AGENTIC_BATCH_SECTIONS=10
KNOWLEDGE_AGENTIC_SKIP_TOKENS=500
KNOWLEDGE_AGENTIC_PROSE_THRESHOLD=0.4
KNOWLEDGE_ENRICH_MODEL=llama3.1
KNOWLEDGE_EMBED_MODEL=nomic-embed-text
KNOWLEDGE_ENRICH_BATCH_SIZE=6
KNOWLEDGE_TOP_K=10
KNOWLEDGE_RRF_K=60
KNOWLEDGE_EXPANSION_COUNT=1
HYBRID_SEARCH_ENABLED=true
HYBRID_SEARCH_KEYWORD_WEIGHT=1.0
HYBRID_SEARCH_VECTOR_WEIGHT=1.0
JUDGE_PROVIDER=ollama
JUDGE_MODEL=llama3.1
gold_standard_path=harness/knowledge_qa/rag_gold_standard.jsonl (118 questions)
```

New for this feature (both legs, once Phase 2 lands):

```
KNOWLEDGE_EVAL_TEMPERATURE=0.0   # greedy decoding (FR-018)
```

Only `IngestionConfig.extraction_mode` (`"docling_text"` vs `"vision"`) differs between the two legs.

**Correction found while building `spot_check.py`** (verified against the live collection): the currently-ingested production ED4_Players_Guide collection (780 chunks) has `extraction_mode="docling_text"` in its chunk metadata, not plain `"docling"`. This is correct and intentional — plain `"docling"` uses Docling's own `HybridChunker`, while `"docling_text"` and `"vision"` both use the shared, configurable `create_chunker()` (`KNOWLEDGE_CHUNKING_STRATEGY=agentic`). The Docling leg of this benchmark uses `extraction_mode="docling_text"` so the chunker is held fixed against the vision leg — using plain `"docling"` would have confounded two variables. All design docs (plan.md, research.md, data-model.md, contracts/, quickstart.md, tasks.md) were updated to reflect this.

---

## Phase 3 — Docling-text leg

### T015 — Ingestion

**Note on a real bug found and fixed here**: the first two ingestion attempts failed identically at ~21.2 min with `ReadTimeout` (during the quality-gate re-split step on large merged sections). Diagnosed with an extended-timeout + per-call-timing instrumented run: confirmed the issue was `OllamaProvider`'s hardcoded 60s httpx timeout being too tight for some large-prompt chunking/enrichment calls under greedy decoding (10-42s per call typically, but some pushed past 60s). Fixed by bumping the timeout to 180s in `packages/llm/llm/providers/ollama.py` (commit `32aa716`) plus a clearer `ProviderUnavailableError` message on timeout. Third attempt (with the extended-timeout diagnostic wrapper, which doubled as the real run) succeeded.

- **Result**: `ingestion_status=ready`, **560 chunks**, `extraction_mode=docling_text` confirmed on every chunk in ChromaDB.
- **Wall-clock**: ~21-25 min (comparable across all 3 attempts to the failure point; not separately measured for the successful full run, but same order of magnitude).

### T016 — Retrieval benchmark

Ran `BENCHMARK_EXTRACTION_MODE=docling_text pytest harness/knowledge_qa/test_gold_standard.py -k recall_sanity -s` (2026-07-08T14:20:12Z). Sanity gate passed (Recall@10=0.9346 ≥ 0.40).

| Category | Questions | MRR | nDCG | Recall@10 |
|---|---|---|---|---|
| direct_fact | 70 | 0.6769 | 0.7208 | 0.9429 |
| comparison | 14 | 0.4724 | 0.6098 | 1.0000 |
| holistic | 12 | 0.7161 | 0.7335 | 0.9042 |
| numeric | 11 | 0.4454 | 0.5281 | 0.7894 |
| relationship | 11 | 0.8652 | 0.8594 | 0.9773 |
| exact_term (subset, n=22) | 22 | 0.6845 | 0.7249 | 0.9432 |
| **Global** | **118** | **0.6526** | **0.7039** | **0.9346** |

Config confirmed held-fixed: chunking=agentic (batch_sections=10, max_tokens=2500, chunking_model=llama3.1, prose_threshold=0.4), enrich_model=llama3.1, embed_model=nomic-embed-text, k=10, hybrid_search_enabled=true (keyword_weight=1.0, vector_weight=1.0), decoding=greedy.

### T017 — Answer-quality (judge)

`eval_runner.py --run-id docling-015` (118/118 questions, 0 errors, 0 empty responses) → `judge_runner.py --run-id docling-015 --summary` (`JUDGE_PROVIDER=ollama`, `JUDGE_MODEL=llama3.1`, greedy). Coverage 118/118 (100%), 0 errors/parse_errors/no_response. Run attribution confirmed: `extraction_mode=docling_text decoding=greedy`.

**Note**: `judge_runner.py`'s progress printout hit a pre-existing Windows console-encoding bug (checkmark char vs cp1252) unrelated to feature 015 — worked around with `PYTHONIOENCODING=utf-8` rather than modifying that file; not fixed in the repo, just noted here.

| Dimension | Mean |
|---|---|
| faithfulness | 0.891 |
| relevance | 0.958 |
| context_utilization | 0.785 |
| answer_correctness | 0.719 |
| **aggregate** | **0.838** |

### T018 — Fidelity spot-check

Ran `spot_check.py --extraction-mode docling_text` (metadata cross-check passed: all sampled chunks confirmed `docling_text`). First pass used a 300-char preview, which was too short to show the actual table row on 3/5 table samples — re-ran with `--preview-chars 1500` for a fair read.

**Chapter openings (10 sampled)**:

| chunk_index | breadcrumb | Verdict |
|---|---|---|
| 0 | (cover page) | N/A — not real prose (roman-numeral/image-placeholder noise), not a drop-cap case |
| 1 | TABLE OF CONTENTS | complete_opening (trivial — TOC heading, no dropped letter) |
| 2 | INTRODUCTION | complete_opening ("The Scourge may be over...") — note: a stray-space artifact "O nce" appears *mid-chunk*, not at the opening, likely a residual drop-cap-adjacent spacing glitch unrelated to this chunk's own opening |
| 3 | The World of Earthdawn | complete_opening |
| 4 | What is a Roleplaying Game? | complete_opening |
| 5 | How to Use This Book | complete_opening |
| 6 | TO THE SADDLE BORN | complete_opening |
| 7 | Steps And Action Dice | complete_opening |
| 8 | Bonus Dice | complete_opening |
| 9 | Steps 1 and 2 | complete_opening |

**9/10 clean complete openings**; 1/10 is degenerate cover-page noise (not a drop-cap defect — a separate, pre-existing structural-noise issue).

**Tables (5 sampled)**:

| chunk_index | breadcrumb | Verdict |
|---|---|---|
| 1 | TABLE OF CONTENTS | **mangled_table** — dot-leader TOC forced into a pipe-table has misaligned rows, empty cells, and multiple entries crammed into one cell |
| 8 | Bonus Dice → Step/Action Dice Table | **coherent_table** — clean 4-column table, correct row pairing |
| 45 | Racial Abilities | not verifiable — no table row visible even at 1500-char preview (tooling limitation: the matched table row is further into the chunk than either preview length) |
| 59 | Assign Attribute Points → Attribute Modifier Cost Table | **coherent_table** — clean 2-column table, correct pairing |
| 61 | Additional Attribute Points Table | **coherent_table** (structure) — but header cell reads "Modiϔier" instead of "Modifier": a ligature/mojibake defect (the "fi" ligature glyph wasn't repaired) distinct from table *structure*, which is otherwise clean |

**3/5 clearly coherent tables, 1/5 clearly mangled (the TOC — expected, since a dot-leader index isn't a real table in the source and forcing it into markdown pipes is inherently lossy), 1/5 unverifiable**. One incidental finding: a ligature-encoding defect ("fi" → "ϔ") not covered by the existing FR-001 mojibake repair table (spec 011) — noted here as a candidate for that repair table's character list, not actioned in this feature.

**Divergence from aggregate metrics**: none apparent yet — will compare against the vision leg's spot-check once available (FR-014).

## Phase 4 — Vision leg

*(pending — filled in when the leg runs)*

## Phase 5 — Comparison & decision

*(pending)*
