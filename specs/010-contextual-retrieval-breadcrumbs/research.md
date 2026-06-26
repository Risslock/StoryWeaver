# Research: Contextual Retrieval, Breadcrumb Injection, Multi-Source Corpus & Per-Category Benchmarking

**Phase 0 output for feature 010** | Resolves all NEEDS CLARIFICATION items from Technical Context

---

## 1. Breadcrumb Extraction — Where and How

**Question**: The current ingestors return `list[str]` chunks. After the cleaned Markdown is chunked, positional context (which heading each chunk fell under) is lost. How do we attach breadcrumbs without changing the chunker interface?

**Decision**: Introduce a `BreadcrumbExtractor` utility class (`packages/rag/rag/knowledge/breadcrumb.py`) that operates on the cleaned Markdown text **before** chunks are passed to enrichment. The pipeline retains the full cleaned text (returned alongside chunks from a new internal path) and calls `BreadcrumbExtractor.extract(md_text, chunks)` to produce a parallel `list[str]` of breadcrumb strings.

**Algorithm**:
1. Scan the full Markdown text line-by-line for ATX headings (`# …`, `## …`, `### …`).
2. Maintain a heading stack keyed by depth (1–3). When a heading at depth D is seen, pop all entries at depth ≥ D and push the new heading.
3. Record `(char_offset, breadcrumb_string)` pairs as the scan progresses.
4. For each chunk, search the full Markdown text for the chunk's first ~80 characters to determine its approximate position. Select the last recorded breadcrumb whose offset is ≤ the chunk's position.
5. Fall back to `doc_title` alone when no heading precedes the chunk (e.g., preamble paragraphs) or when the chunk text is not locatable in the Markdown (possible with agentic chunker rewrites).

**Breadcrumb format**: `"{doc_name} > {H1}" `, `"{doc_name} > {H1} > {H2}"`, etc. The document name is the cleaned filename stem (same value that flows through the pipeline as `doc_title`).

**Alternatives considered**:
- Modify each chunker to pass heading context alongside each chunk — rejected because it requires changes to three chunker implementations and complicates the `BaseChunker` interface.
- Extract headings from each chunk's own text — rejected because chunks that start mid-section carry no heading marker; would miss most chunks.
- Use pymupdf4llm's `toc` (table of contents) output for PDFs — promising but pymupdf4llm's `page_chunks=True` mode does not expose a reliable per-paragraph heading path. Heading scanning from the rendered Markdown is more portable and works for both PDF and Markdown ingestors.

**Rationale**: The Markdown text is already available inside `ingestor.py` before `self._chunker.async_chunk(text)` is called. The ingestor needs one small extension: a method that returns `(full_md_text, chunks)` so the pipeline can run the extractor. No chunker changes required.

---

## 2. Breadcrumb Storage

**Question**: Should the breadcrumb be part of `original_text` in ChromaDB metadata, or stored as a separate `breadcrumb` metadata field, or both?

**Decision**: Both.
- `original_text` in ChromaDB = `"{breadcrumb}\n\n{raw_chunk_text}"` — ensures the breadcrumb is visible wherever `KnowledgeChunk.text` is displayed to the GM.
- `breadcrumb` stored as a separate string metadata field — enables structured display and future filtering.
- `KnowledgeChunk` gains a `breadcrumb: str = ""` field populated from the metadata field.

**Rationale**: Storing the breadcrumb in `original_text` satisfies US2 acceptance scenario 1 ("the stored chunk text begins with a breadcrumb") and scenario 2 (visible in the UI). The separate metadata field supports structured access without parsing the text.

---

## 3. Contextual Summary Prompt Design

**Question**: What prompt produces useful 1–2 sentence situating summaries that improve semantic retrieval without hallucinating?

**Decision**: Use a two-part prompt passed to the existing `OllamaProvider` via `ChunkEnricher.generate_contextual_summary()`:

System prompt:
```
You are a retrieval assistant. Your task is to write a one or two sentence description
that situates a text passage within its source document, for the purpose of improving
search retrieval. Be factual and concise. Do not repeat the passage text verbatim.
```

User prompt:
```
Document: {doc_title}
Section: {breadcrumb}

Passage:
{chunk_text}

Write one or two sentences situating this passage within the document for search retrieval.
```

The document context uses `doc_title` + `breadcrumb` rather than the full document text, which would exceed Ollama context windows for large rulebooks.

**Fallback**: If the LLM call raises any exception (including `ProviderUnavailableError`), the chunk is ingested without a contextual summary — breadcrumb + headline + enrichment.summary + raw text is used instead. The failure is logged at WARNING level.

**Compound text order** (with breadcrumbs + contextual summaries enabled):
```
{breadcrumb}

{contextual_summary}

{headline}

{enrichment.summary}

{raw_chunk_text}
```

**Alternatives considered**: Using the full document text as context (Anthropic's original contextual retrieval approach) — rejected because full rulebook PDFs (200+ pages) exceed local Ollama context windows. Using a sliding window of surrounding chunks — adds complexity and pipeline state; deferred.

---

## 4. Pipeline Cleanup — IngestionConfig

**Question**: `IngestionPipeline.run()` has accumulated `source_type`, `access_level_default`, `cleaning` (in the ingestor), and is now about to receive `enable_breadcrumbs` and `enable_contextual_summaries`. How do we avoid this growing forever?

**Decision**: Introduce `IngestionConfig` — a plain Python dataclass that groups all preprocessing options. `run()` takes `(doc_id, file_path, format, scope, campaign_id, config: IngestionConfig = IngestionConfig())`. Every future preprocessing option is added to `IngestionConfig`, never to `run()`.

**What moves into `IngestionConfig`**:
- `source_type` (was a `run()` kwarg)
- `access_level_default` (was a `run()` kwarg)
- `cleaning` (was a `ingest_async()` param extracted from env var)
- `enable_breadcrumbs` (new)
- `enable_contextual_summaries` (new)

**What stays in `run()`**: only document identity (`doc_id`, `file_path`, `format`) and storage routing (`scope`, `campaign_id`). These describe WHERE and WHAT, not HOW.

**Migration**: The only production caller (`apps/web/services/knowledge.py:_run_pipeline()`) is updated to construct `IngestionConfig(source_type=..., access_level_default=...)` and pass it. Tests that call `ingest()` directly are unaffected — `IngestionConfig` is a pipeline concern.

**Rationale**: Without this change, every new ingestion option in future specs would expand the `run()` signature. A config object is the established pattern for this problem; it also makes the Gradio upload form mapping natural (form fields map 1:1 to config fields).

---

## 6. Source-Type Metadata — Tag Only, No Retrieval Filter

**Question**: Should `source_type` be a retrieval-time filter parameter?

**Decision**: No retrieval filter. The `source_type` value is stored as a metadata field on every chunk in ChromaDB (new field `source_type` in the `metadatas` dict). No `where` clause filter is added to `ChromaKnowledgeRetriever.search()`. The LLM and system prompt at chat interaction time provide source-type awareness — no code-level gating is needed or desired.

**What is implemented**:
- `IngestionPipeline.run()` accepts `source_type: str = "rulebook"` (already present in the current codebase).
- `_build_records()` writes `source_type` into each chunk's ChromaDB metadata (currently missing from `_build_records` — it accepts `source_type` in `run()` but does not propagate it to metadata).
- `KnowledgeChunk` gains a `source_type: str = "rulebook"` field populated when retrieving.

**Rationale**: The user explicitly confirmed that source-type awareness belongs in the LLM/prompt layer, not as a hard retrieval filter. Storing the tag preserves the option for future tooling without forcing premature filtering logic.

---

## 5. Per-Category Benchmarking — EvalSummary Extension

**Question**: How to extend `EvalSummary` and `benchmark_results.jsonl` for per-category metrics without breaking existing records or callers?

**Decision**:
- Add a new `CategoryMetrics` Pydantic model: `mean_mrr`, `mean_ndcg`, `mean_recall_at_k`, `question_count`.
- Add `category_scores: dict[str, CategoryMetrics] = {}` to `EvalSummary` (optional with default empty dict — existing deserialisations remain valid).
- Extend `aggregate_results()` to group `RetrievalEvalResult` by `category`, compute per-group stats, and populate `category_scores`. Questions with no `category` field land in `"uncategorized"`.
- The benchmark harness (`test_gold_standard.py`) serialises `category_scores` into the JSONL record and prints a per-category table to stdout.
- `RetrievalEvalResult.category` is already populated from `TestQuestion.category` — no gold standard changes needed.

**Backward compatibility**: Existing `benchmark_results.jsonl` records without `category_scores` remain valid. New records include it. No migration required.

---

## 8. Empirical Chunk Quality Analysis — ED4_Players_Guide Corpus

**Date**: 2026-06-26 | **Collection**: `knowledge_global` | **Total chunks**: 1206 | **Source**: single PDF (`ED4_Players_Guide`), all `source_type=rulebook`

### Length distribution

| Range | Count | % |
|---|---|---|
| 0–100 chars | 5 | 0.4% |
| 100–300 chars | 213 | 17.7% |
| 300–1000 chars | 555 | 46.0% |
| 1000–3000 chars | 388 | 32.2% |
| 3000–10000 chars | 38 | 3.2% |
| >10000 chars | 7 | 0.6% |
| **avg** | **1032 chars** | max: 34066, min: 37 |

### Problem categories (with concrete examples)

**P1 — Encoding artifacts / mojibake** (pervasive, high severity)
Windows-1252 → UTF-8 mismatch leaves `�` replacement characters throughout.
```
"Player�s Guide"   → Player's Guide
"subtracts �2"     → subtracts −2 (minus sign)
"T￼lanthyn"        → T'lanthyn (curly apostrophe)
"adds +3 to his Attack�increasing"  → em-dash
```
Affects curly quotes, apostrophes, em-dashes, minus signs, and special characters everywhere.

**P2 — Drop-cap OCR failures** (every chapter opening, high severity)
PDF drop caps (oversized first letter in a separate text box) are extracted as isolated characters and dropped, breaking the first sentence of every chapter.
```
"nce, long ago, the land grew lush..."    → "Once, long ago..."
"avon woke to the smell of smoke..."      → "Davon woke to..."
"his chapter introduces you to..."        → "This chapter..."
```

**P3 — Giant unsplit chunks** (7 chunks > 10k chars, high severity)
- chunk_index=9: **34,066 chars** — entire "TO THE SADDLE BORN" narrative chapter as one vector
- chunk_index=1: **18,684 chars** — Credits + Kickstarter backer list
- chunk_index=1203–1205: 12–13k chars — full A–Z book index tables
These chunks are practically unembeddable as semantic units and will never match a player query.

**P4 — TOC / Credits / Index pages not filtered** (high severity)
Table of Contents (10k chars) contains only dot leaders `CREDITS ................................2`. Full index tables. Kickstarter backer name lists. These should be detected and skipped during ingestion. The LLM enricher labeled the TOC chunk "Introduction and Game Basics" — a hallucination caused by noisy input.

**P5 — Stub/fragment chunks** (5 chunks < 100 chars, medium severity)
```
chunk_index=640: "265)."                                     (37 chars)
chunk_index=107: "## **8."                                   (56 chars)
chunk_index=546: "Everything has a pattern."                 (77 chars)
```
Orphaned cross-reference numbers, heading fragments, or single-sentence stubs from page-split overflow.

**P6 — Mid-word / mid-sentence splits** (medium severity)
Chunker split at a PDF hard line-wrap, then the broken line propagated as the breadcrumb.
```
breadcrumb: "animal husbandry and first aid. Beast-"
text:       "masters may use half-magic when recognizing..."

text: "**Novice Talent Options:** Acro-\nbatic Defense..."
```

**P7 — Image placeholder markup left in text** (medium severity)
```
"**==> picture [360 x 287] intentionally omitted <==**"
"**----- Start of picture text -----**<br>Ulm wants to retrieve a key..."
```
The picture caption text (rendered alt-text inside the image box) also leaks through in some chunks.

**P8 — Stranded page numbers** (medium severity)
PDF page footer numbers appear as standalone lines inside chunks:
```
"...Tail Attack!\n\n66"
"...warm place.\n\n14\n\n\n**==> picture ..."
```

**P9 — Broken table structure** (medium severity)
Tables from multi-column PDF layouts have duplicated/misaligned headers:
```
"||||**Namegiver**|**Namegiver**|**Races**|**Summary**|**Summary**|||"
"|---|---|---|---|---|---|---|---|---|---|"
"|Dwarf|Dex|9|Str 10|Tou 12|Per 11|Wil 11|Cha 10|10|4|"
```

**P10 — Breadcrumb quality issues** (medium severity)
- Decorative / meaningless: `ED4_Players_Guide > **K**` (cover art letter K)
- Mid-sentence: `ED4_Players_Guide > animal husbandry and first aid. Beast-`
- Bold/italic markers inside breadcrumb: `> _**Versatility**_`, `> **Important Attributes:** Charisma…`
- Collision: 4+ chunks share `ED4_Players_Guide > INTRODUCTION` with no sub-heading differentiation
- Every breadcrumb starts with `ED4_Players_Guide >` — first segment adds no retrieval discrimination within a single-doc corpus

**P11 — LLM enricher hallucinations on garbage input** (compounding)
When P1/P2/P4 produce noisy input, the enricher generates plausible-sounding but wrong metadata:
```
chunk_index=0  (OCR garbage: "a", "I I", "II", "III"...)
  headline: "Session Preparation"
  topic:    "gm_only/sessions/storylines"
  access_level: player_visible  (should be filtered out entirely)
```

### Good chunk baseline (what correct output looks like)

**chunk_index=97** (887 chars) — self-contained rule, clean boundaries:
```
breadcrumb: ED4_Players_Guide > _**Versatility**_
headline:   Human Adepts and Versatility
summary:    Human adepts can acquire talents from other Disciplines with Versatility, but may advance Circles slower.
text:       [complete explanation of Versatility talent with cross-reference]
```

**chunk_index=14** (492 chars) — focused rule with example:
```
breadcrumb: ED4_Players_Guide > Bonuses and Penalties
headline:   Bonuses and Penalties
summary:    Explanation of how bonuses and penalties modify test results in Earthdawn.
text:       [explains modifier to Step, includes worked example]
```

### Prioritised improvement areas for future specs

| # | Area | Issue | Severity |
|---|---|---|---|
| 1 | **Cleaning** | Windows-1252 → UTF-8 encoding fix (re-extract or chardet) | High |
| 2 | **Cleaning** | Drop-cap sentence-start repair (detect isolated uppercase chars at start of text blocks) | High |
| 3 | **Chunking** | Filter / skip structural-noise pages: TOC, Credits, Index, backer lists | High |
| 4 | **Chunking** | Giant narrative chapter re-split (detect > N tokens, force semantic re-chunk) | High |
| 5 | **Cleaning** | Strip image placeholder markup (`==> picture … <==`, picture text fences) | Medium |
| 6 | **Cleaning** | Strip stranded page-number lines (bare integer on its own line) | Medium |
| 7 | **Chunking** | Merge stub chunks (< ~150 chars after breadcrumb) with next sibling | Medium |
| 8 | **Chunking** | Detect + rejoin mid-word PDF line-wrap breaks (`Word-\nbreak` pattern) | Medium |
| 9 | **Markdown extraction** | Normalise broken table headers from multi-column PDF layout | Medium |
| 10 | **Breadcrumbs** | Strip bold/italic markdown from breadcrumb path segments | Low |
| 11 | **Breadcrumbs** | Deduplicate colliding breadcrumbs (append sub-heading counter or paragraph index) | Medium |
| 12 | **Retrieval** | Omit `doc_title` prefix from the embedded compound text when corpus is single-doc | Low |

---

## 7. ChromaDB Metadata Field: `source_type`

**Question**: `pipeline.py._build_records()` currently receives `source_type` via `run()` but does not write it into the ChromaDB metadata dict. Is this intentional?

**Finding**: Unintentional gap. The `source_type` parameter was added to `run()` and passed to `_extract_chunks()` (which uses it for cleaning rules), but was never forwarded into `_build_records()` as a stored metadata field.

**Decision**: Fix this gap as part of feature 010 — add `"source_type": source_type` to the metadata dict in `_build_records()`. This is a non-breaking addition; existing chunks in the index simply lack this field, which ChromaDB returns as absent (handled by `.get("source_type", "rulebook")` fallback in the retriever).
