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

### T019/T020 — Ingestion

Two failed attempts before success, each teaching something real about `KNOWLEDGE_EVAL_TEMPERATURE=0.0` (greedy decoding) interacting with large prompts:

1. **Attempt 1** (180s timeout): vision extraction of all 524 pages succeeded (~109 min), chunking/quality-gate produced 288 chunks, but the first batch-enrichment call exceeded 180s → `ProviderUnavailableError`. Collection left clean (0 chunks — nothing had been upserted yet).
2. **Attempt 2** (600s timeout, per explicit user direction given the ~109-min cost of retrying): succeeded end-to-end.

**Fix applied**: bumped `OllamaProvider`'s httpx timeout 180s → 600s (`packages/llm/llm/providers/ollama.py`, commit `0fabed8`). This is now the second bump in this feature (60s → 180s → 600s) — greedy decoding on large chunk-enrichment/boundary-detection prompts is consistently slower than Ollama's uncontrolled default temperature was.

- **Result**: `ingestion_status=ready`, **282 chunks**, `extraction_mode=vision` confirmed on every chunk in ChromaDB.
- **Wall-clock (FR-017)**: successful attempt took **118.6 minutes** (7118.8s) end-to-end (vision extraction + chunking/quality-gate + enrichment/embedding/storage of 282 chunks across 47 batches). This is above the spec's 30–90 min estimate — driven by 524 individual per-page vision-model calls plus greedy-decoding enrichment, not by any single defect.
- **Smoke query** (SC-001, US1 AC3): `"What is a bonus die?"` → 5 non-empty ranked results, top hit `"Bonus Dice and Step/Action Dice Table"` — relevant and correctly populated.

### T021 — Retrieval benchmark

Ran `BENCHMARK_EXTRACTION_MODE=vision pytest harness/knowledge_qa/test_gold_standard.py -k recall_sanity -s`. Sanity gate passed (Recall@10=0.9508 ≥ 0.40).

| Category | Questions | MRR | nDCG | Recall@10 |
|---|---|---|---|---|
| direct_fact | 70 | 0.6394 | 0.7008 | 0.9612 |
| comparison | 14 | 0.4695 | 0.5914 | 0.9714 |
| holistic | 12 | 0.6194 | 0.6724 | 0.8792 |
| numeric | 11 | 0.6360 | 0.6531 | 0.8939 |
| relationship | 11 | 0.6033 | 0.7273 | 1.0000 |
| **Global** | **118** | **0.6127** | **0.6831** | **0.9508** |

**Comparability confirmed** (`assert_comparable_extraction_runs`, T024 satisfied for the retrieval records): the two fresh benchmark records differ **only** in `extraction_mode` (docling_text vs vision) — all held-fixed fields identical (chunking/enrich_model=llama3.1/embed_model=nomic-embed-text/k=10/hybrid_search config/gold_standard_path/decoding=greedy).

### T022 — Answer-quality (judge)

`eval_runner.py --run-id vision-015` (118/118 questions, 0 errors, 0 empty responses) → `judge_runner.py --run-id vision-015 --summary`. Coverage 118/118 (100%), 0 errors/parse_errors/no_response. Run attribution confirmed: `extraction_mode=vision decoding=greedy`.

| Dimension | Docling-text | Vision | Δ (vision − docling) |
|---|---|---|---|
| faithfulness | 0.891 | 0.678 | **−21.3 pp** |
| relevance | 0.958 | 0.872 | −8.6 pp |
| context_utilization | 0.785 | 0.565 | **−22.0 pp** |
| answer_correctness | 0.719 | 0.471 | **−24.8 pp** |
| **aggregate** | **0.838** | **0.647** | **−19.1 pp** |

**This is a major, unambiguous regression** — every dimension worse, aggregate −19.1pp against a 1.0pp non-inferiority tolerance (FR-008). Notably this happens *despite* vision's slightly better retrieval Recall@10 (0.951 vs 0.935): a clear "good recall, bad answers" gap — vision retrieves relevant-looking chunks, but their text content is evidently less reliable for the answer LLM to construct faithful, correct answers from. See spot-check (T023) for a qualitative look at why.

### T023 — Fidelity spot-check

Ran `spot_check.py --extraction-mode vision --preview-chars 1500` (metadata cross-check passed).

**Chapter openings (10 sampled)**:

| chunk_index | breadcrumb | Verdict |
|---|---|---|
| 0 | (cover page) | N/A — not real prose |
| 1 | INTRODUCTION | **drop_cap_gap** — body reads `"O\nnce, long ago..."` (should be "Once, long ago"); the drop-cap letter is isolated on its own line, not rejoined |
| 3 | EARTHDAWN (fiction intro) | complete_opening ("Anna clutched at Davon...") — but chunk *ends* with a stray orphaned `"T"` on its own line, which is the drop-cap letter belonging to the *next* chunk's heading, split across the chunk boundary |
| 4 | GAME CONCEPTS | **drop_cap_gap** — body reads `"T\nhis chapter introduces..."` (should be "This chapter"); same defect as chunk 1, and the orphaned "T" noted in chunk 3 appears to be a duplicate/misplaced copy of this same drop-cap letter |
| 5 | BONUS DICE | complete_opening |
| 6 | Steps 1 and 2 | complete_opening |
| 7 | Bonuses and Penalties | complete_opening |
| 8 | Test Results | complete_opening |
| 9 | Optional Rules | complete_opening |
| 10 | EFFECT TESTS | complete_opening |

**7/10 clean, 2/10 clear drop-cap-gap failures, 1/10 N/A.** This is *worse* than the docling_text leg's 9/10 clean rate on the same defect class — directly contradicting the spec-011 hypothesis that vision extraction would fix drop-caps better than text extraction. The vision model appears to visually reproduce the drop-cap layout (isolated large first letter) as literal isolated text rather than reading it as part of the word, and chunk boundaries can split it further.

**Tables (5 sampled)**:

| chunk_index | breadcrumb | Verdict |
|---|---|---|
| 0 | (cover/credits) | N/A — not a real table |
| 5 | BONUS DICE → Step/Action Dice Table | **mangled_table** — the table's own title row became a spurious data row (`\| **Step/Action Dice Table** \|  \|`), and rows are crammed with literal `&nbsp;&nbsp;` HTML-entity padding into single cells instead of being split into proper columns |
| 30 | Racial Abilities | not verifiable — no table row visible even at 1500-char preview |
| 42 | Mystic Armor Table | **coherent_table** — clean, correctly-paired 30-row table |
| 43 | Armor Ratings | not verifiable — no table row visible within preview |

**1/5 clearly coherent, 1/5 clearly mangled, 1/5 N/A, 2/5 unverifiable.** The mangled case (chunk 5, Step/Action Dice Table) is the *same table* sampled from the docling_text leg (there, chunk_index=8, "Bonus Dice"), which was clean and correctly structured — a **direct, same-content regression**: Docling extracted this exact table correctly; vision did not.

**Divergence from aggregate metrics (FR-014)**: this spot-check is *consistent with*, not divergent from, the aggregate judge-score regression (−19.1pp) — it gives a concrete qualitative explanation for it. Vision's slightly higher Recall@10 reflects that *relevant chunks are still being found*, but the drop-cap and table-mangling defects mean the *text content* of those chunks is measurably less reliable for the answer LLM to build faithful, correct answers from — directly explaining why `context_utilization` and `answer_correctness` cratered even as retrieval held up.

## Phase 5 — Comparison & decision

### T024 — Comparability confirmed

`assert_comparable_extraction_runs()` passed on the two fresh records (2026-07-08T14:20:12Z docling_text, 2026-07-09T00:53:23Z vision): every held-fixed field identical (chunking config, enrich_model=llama3.1, embed_model=nomic-embed-text, k=10, hybrid_search_enabled=true/keyword_weight=1.0/vector_weight=1.0, decoding=greedy, gold_standard_path) — only `extraction_mode` differs (SC-005).

### T025 — Per-category retrieval diff

`compare_benchmark_runs(-2, -1)` (A=docling_text, B=vision):

| Category | MRR-A | MRR-B | ΔMRR | nDCG-A | nDCG-B | ΔnDCG | Recall-A | Recall-B | ΔRecall |
|---|---|---|---|---|---|---|---|---|---|
| comparison | 0.4724 | 0.4690 | −0.0034 | 0.6098 | 0.5908 | −0.0190 | 1.0000 | 0.9714 | −0.0286 |
| direct_fact | 0.6769 | 0.6387 | −0.0382 | 0.7208 | 0.7006 | −0.0202 | 0.9429 | 0.9610 | +0.0181 |
| holistic | 0.7161 | 0.6186 | −0.0975 | 0.7335 | 0.6719 | −0.0616 | 0.9042 | 0.8792 | −0.0250 |
| numeric | 0.4454 | 0.6364 | **+0.1910** | 0.5281 | 0.6527 | **+0.1246** | 0.7894 | 0.8939 | **+0.1045** |
| relationship | 0.8652 | 0.6033 | **−0.2619** | 0.8594 | 0.7274 | **−0.1320** | 0.9773 | 1.0000 | +0.0227 |
| exact_term (n=22) | 0.6845 | 0.8267 | **+0.1422** | 0.7249 | 0.8166 | **+0.0917** | 0.9432 | 0.9848 | +0.0416 |
| **global** | 0.6526 | 0.6130 | −0.0396 | 0.7039 | 0.6827 | −0.0212 | 0.9346 | 0.9513 | +0.0167 |

**Retrieval picture is genuinely mixed**: vision clearly *wins* on `numeric` and the `exact_term` subset (biggest deltas in the whole table), clearly *loses* on `relationship` (biggest single-category loss) and `holistic`, and is roughly flat elsewhere. Global retrieval is a near-wash (marginally better Recall, marginally worse MRR/nDCG) — retrieval alone would not obviously favor either path.

### T026 — Judge delta vs tolerance

Judge aggregate delta (vision − docling_text) = **0.647 − 0.838 = −0.191 (−19.1 pp)**, against the FR-008 fixed non-inferiority tolerance of **1.0 pp**. This is **19x past tolerance** — not a borderline call. Every judge dimension regressed (see T022 table). Global Recall@10 delta = +1.67pp — within the "no material regression" band (2pp threshold) on its own, but retrieval is the *secondary* signal and does not override the primary gate.

### T027 — Spot-check vs aggregate-metric divergence

No divergence — see T023: the spot-check (2/10 chapter-opening drop-cap failures vs docling's 0/10; 1/5 tables mangled including a *direct same-content regression* on the Step/Action Dice Table) is consistent with and explains the judge-score regression, not in tension with it.

### T028 — Recommendation

**Applying the FR-008 decision rule**: the global LLM-judge aggregate is the primary gate. Vision is recommended as default only if its judge score is non-inferior to Docling within 1.0pp AND global retrieval does not materially regress (2pp threshold). Vision's judge aggregate regressed by −19.1pp — far past the tolerance — so per FR-008 the recommendation is **keep-Docling (`docling_text`) as the default extraction path, regardless of retrieval gains**.

> ## RECOMMENDATION: **`docling_default`** — keep `docling_text` as the default PDF extraction path. Do NOT switch to `vision`.
>
> **Primary gate (decisive)**: judge aggregate −19.1pp (0.838 → 0.647), vs a 1.0pp non-inferiority tolerance. Every judge dimension regressed; answer_correctness fell the most (−24.8pp).
>
> **Supporting evidence**: global retrieval is a near-wash (Recall@10 +1.67pp, MRR −3.96pp, nDCG −2.12pp) — not itself disqualifying, and would not have overridden the judge gate even if more favorable. Retrieval is genuinely better for `numeric` and exact-term-lookup questions (+10-19pp), suggesting vision has real, narrow strengths — but not enough to outweigh the broad answer-quality collapse.
>
> **Qualitative cause (spot-check)**: vision extraction did not fix drop-caps as hypothesized (2/10 sampled openings still show the literal split-letter defect, e.g. `"O\nnce, long ago"`, vs 0/10 for docling_text) and produced a *directly worse* rendering of at least one table that Docling extracted cleanly (Step/Action Dice Table). This gives a concrete mechanism for the judge regression: the answer LLM is working from measurably lower-fidelity context text.
>
> **Operational cost**: vision ingestion took 118.6 minutes (successful run) — well above Docling's ~21-25 minutes — and required two code-level reliability fixes (timeout bumps to 180s then 600s) to complete without failing on large-prompt LLM calls. This is a real, independent cost against adopting vision as a default path, on top of the quality regression.
>
> **Limitation**: per FR-018, this is a single ingestion + single evaluation pass per path with greedy decoding to minimize variance, not multiple repeated runs — residual local-model nondeterminism is not fully eliminated. However, a −19.1pp aggregate delta is far too large to plausibly be noise at temperature 0; this limitation does not call the verdict into question.
>
> **Note for future work**: vision's advantage on `numeric`/exact-term questions and the model/prompt-dependent nature of the drop-cap and table defects suggest vision extraction *could* be revisited with a different vision model, an improved extraction prompt, or a hybrid approach (e.g., vision only for image-heavy/table-heavy sections) — but that is prompt/model tuning, explicitly out of scope for this feature (FR-015) and belongs in backlog spec 016 or a dedicated follow-up, not this benchmark.
