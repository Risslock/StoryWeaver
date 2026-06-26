# Tasks: Corpus Pre-Processing & Cleaning

**Input**: Design documents from `specs/008-corpus-cleaning/`

**Branch**: `008-corpus-cleaning` | **Date**: 2026-06-25

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

**Design refs**: [data-model.md](data-model.md) | [contracts/cleaner-api.md](contracts/cleaner-api.md) | [research.md](research.md) | [quickstart.md](quickstart.md)

**Tests**: Included â€” FR-012 explicitly requires independently testable cleaning (plain MD in/out).

---

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no code dependency on an incomplete task)
- **[US1/US2/US3]**: Which user story this task belongs to
- Exact file paths are included in every task description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create new file stubs so Phase 2 tasks can begin without file-not-found errors.

- [X] T001 Create `packages/rag/rag/knowledge/cleaner.py` with module docstring, import block (`re`, `logging`, `dataclasses`, `typing`), and `__all__` stub only â€” no logic yet
- [X] T002 [P] Create `packages/rag/tests/knowledge/test_cleaner.py` with import block (`pytest`, `CorpusCleaner`, `PageText`, `CleanedDocument`) and a single placeholder `test_placeholder` that passes
- [X] T003 [P] Create `packages/core/core/migrations/versions/0007_add_source_type_to_knowledge_documents.py` with `upgrade()` adding `source_type STRING(20) NOT NULL server_default='rulebook'` to `knowledge_documents` and `downgrade()` dropping it

**Checkpoint**: Three new files exist. The existing test suite still passes.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Wire the source_type propagation chain end-to-end and upgrade PDF extraction to
`page_chunks=True`. All user story phases depend on this being complete.

**âš ï¸ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Implement all public data types in `packages/rag/rag/knowledge/cleaner.py`: `SourceType` literal, `PageText` dataclass (`page_num: int, text: str`), `CleaningReport` dataclass (6 fields + `warnings: list[str]`), `CleanedDocument` dataclass (`text`, `source_type`, `report`), `CleaningRuleProfile` dataclass (5 bool fields), `_PROFILES: dict[SourceType, CleaningRuleProfile]` mapping (4 source types per rule profile matrix in data-model.md), and `CorpusCleaner` class with stub `clean_pages(pages, source_type) -> CleanedDocument` that joins pages without applying rules, and `clean_text(text, source_type) -> CleanedDocument` that wraps text in `PageText(page_num=0)` and delegates to `clean_pages`
- [X] T005 [P] Add `source_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="rulebook")` to `KnowledgeDocument` in `packages/core/core/models.py`, then run `uv run alembic upgrade head` to apply migration T003
- [X] T006 Upgrade `PdfIngestor` in `packages/rag/rag/knowledge/ingestor.py`: change `_convert_to_markdown()` to call `pymupdf4llm.to_markdown(file_path, page_chunks=True)` and return `list[PageText]` (mapping `chunk["metadata"]["page"]` â†’ `page_num`, `chunk["text"]` â†’ `text`); add `source_type: str = "rulebook"` and `cleaning: bool = True` params to `PdfIngestor.ingest_async()`; add same params to `MarkdownIngestor.ingest_async()`; call `CorpusCleaner().clean_pages(pages, source_type)` (or `clean_text` for Markdown) when `cleaning=True`, else join pages directly
- [X] T007 Add `source_type: str = "rulebook"` to `IngestionPipeline.run()` signature in `packages/rag/rag/knowledge/pipeline.py`; propagate to `_extract_chunks(file_path, format, source_type)`; in `_extract_chunks`, read `KNOWLEDGE_CLEANING_ENABLED` and `KNOWLEDGE_CLEANING_FRONTMATTER_PAGES` env vars and pass `cleaning=enabled` to ingestor; pass `KNOWLEDGE_CLEANING_FRONTMATTER_PAGES` as constructor param or call-time param to `CorpusCleaner`
- [X] T008 Add `source_type: str = "rulebook"` to `submit_document()`, `confirm_overwrite()`, and `_run_pipeline()` in `apps/web/services/knowledge.py`; propagate to `pipeline.run(source_type=...)` and persist as `KnowledgeDocument.source_type` on the document record
- [X] T009 Add `source_type_dd = gr.Dropdown(choices=["rulebook","supplement","novel","handwritten"], value="rulebook", label="Source type", elem_id="gm-knowledge-source-type")` to the upload accordion in `apps/web/pages/gm/knowledge_qa.py`; wire as extra input to `on_upload()` and `on_confirm_overwrite()` event handlers; add "Source" display column to the ingested documents table

**Checkpoint**: Pipeline runs end-to-end with source_type propagated and logged; cleaning stubs join pages without transformation; dropout selects source_type; existing unit tests pass.

---

## Phase 3: User Story 1 â€” Structured Layouts Retrieved Accurately (Priority: P1) ðŸŽ¯ MVP

**Goal**: Multi-column tables, stat blocks, and creature example blocks are reconstructed into
coherent Markdown before reaching the chunker. The GM can query `"What are the attribute
modifiers for a Windling?"` and receive correctly ordered content, not interleaved fragments.

**Independent Test**: `uv run pytest packages/rag/tests/knowledge/test_cleaner.py -k "us1 or multicolumn or stat_block or creature" -v` â€” all pass without Ollama.

### Tests for User Story 1

> **Write these first â€” they MUST FAIL before implementation begins (T011â€“T014)**

- [X] T010 [US1] Write failing tests for US1 in `packages/rag/tests/knowledge/test_cleaner.py`:
  - `test_stat_block_reconstructed_as_markdown_table`: fixture with 4 lines containing Earthdawn keywords (`DEX: 6  STR: 8  TOU: 9`, `Initiative: 5`, `Wounds: 10`, `Physical Armor: 4`) â†’ `CleanedDocument.text` contains `| Attribute | Value |` table rows; `report.stat_blocks_reconstructed == 1`
  - `test_stat_block_not_triggered_below_threshold`: only 2 keyword lines â†’ block preserved as-is; `report.stat_blocks_reconstructed == 0`
  - `test_creature_block_preserved_contiguously`: fixture with `## Windling Thief` heading, 2 prose sentences, 3 stat lines â†’ heading and all content appear in one contiguous section; no fragmentation
  - `test_source_type_novel_skips_stat_block`: same stat-block fixture with `source_type="novel"` â†’ block unchanged; `report.stat_blocks_reconstructed == 0`
  - `test_source_type_handwritten_skips_stat_block`: same fixture with `source_type="handwritten"` â†’ block unchanged

### Implementation for User Story 1

- [X] T011 [P][US1] Implement fitz block coordinate extraction and multi-column reconstruction in `packages/rag/rag/knowledge/ingestor.py`: add `_extract_multicolumn_page(fitz_page) -> str | None` private method that calls `fitz_page.get_text("dict")["blocks"]`, clusters blocks by x0 coordinate (column gap > 20% page width = multi-column), sorts each cluster by y0, interleaves rows, and returns reordered Markdown text; returns `None` for single-column pages; annotate with `WARNING` log per contract format when multi-column is reconstructed
- [X] T012 [P][US1] Implement stat block detection and normalisation in `packages/rag/rag/knowledge/cleaner.py`: add `_reconstruct_stat_blocks(text: str, doc_name: str) -> tuple[str, int]` that finds groups of â‰¥ 3 consecutive short lines (â‰¤ 80 chars) containing Earthdawn 4E keywords (`DEX`, `STR`, `TOU`, `PER`, `WIL`, `CHA`, `Initiative`, `Wounds`, `Unconsciousness`, `Death`, `Armor`, `Mystic`, `Physical`, `Step`, `Action`, `Attacks`, `Damage`), converts them to `| Attribute | Value |` Markdown table rows, logs at WARNING per contract format, and returns (modified_text, count)
- [X] T013 [US1] Implement creature example block preservation in `packages/rag/rag/knowledge/cleaner.py`: add `_preserve_creature_blocks(text: str) -> str` that identifies Markdown sections (content between heading markers) containing both â‰¥ 2 prose sentences and â‰¥ 1 embedded stat-block pattern; marks them with a DEBUG log to confirm they were recognised; returns text unchanged (these blocks are already contiguous â€” no splitting is needed, just the log)
- [X] T014 [US1] Wire US1 rules into `CorpusCleaner.clean_pages()` in `packages/rag/rag/knowledge/cleaner.py`: when `profile.stat_block_reconstruction` is True, call `_reconstruct_stat_blocks()` on joined text and update `report.stat_blocks_reconstructed`; call `_preserve_creature_blocks()` on joined text (log only); in `PdfIngestor.ingest_async()` in `packages/rag/rag/knowledge/ingestor.py`, open a parallel `fitz.open()` pass and for each page call `_extract_multicolumn_page()` â€” if it returns a string, replace the corresponding `PageText.text` before handing to the cleaner; update `report.multicolumn_pages_reconstructed`

**Checkpoint**: `test_cleaner.py` US1 tests all pass. Ingest a PDF with stat blocks and run `"What are the DEX, STR, and TOU steps for a Windling?"` â€” returned chunk is a coherent table, not scrambled lines.

---

## Phase 4: User Story 2 â€” Rule Text Searchable Without Hyphenation Breaks (Priority: P1)

**Goal**: All hyphenated line-break splits (`word-\ncontinuation`) are rejoined before the
chunker indexes the text. Terms like `karma`, `talent`, and `character` are discoverable by
natural-language queries even if the PDF split them at a column or page boundary.

**Independent Test**: `uv run pytest packages/rag/tests/knowledge/test_cleaner.py -k "dehyphen" -v`

### Tests for User Story 2

> **Write these first â€” they MUST FAIL before T016**

- [X] T015 [US2] Write failing tests for de-hyphenation in `packages/rag/tests/knowledge/test_cleaner.py`:
  - `test_dehyphen_line_break_joined`: `"kar-\nma"` â†’ `"karma"`; `"tal-\nent"` â†’ `"talent"`
  - `test_dehyphen_preserves_intentional_hyphen`: `"one-shot"`, `"half-magic"`, `"step-based"` all unchanged (no newline after hyphen)
  - `test_dehyphen_preserves_list_marker`: `"- item one\n- item two"` unchanged (hyphen at line start, no preceding word char)
  - `test_dehyphen_cross_page_boundary`: two-page `list[PageText]` where page 0 ends `"kar-"` and page 1 starts `"ma"` â†’ joined text is `"karma"` (cross-page break caught at join time); `report.hyphens_rejoined == 1`
  - `test_dehyphen_count_in_report`: text with 3 hyphenated breaks â†’ `report.hyphens_rejoined == 3`
  - `test_dehyphen_applies_to_all_source_types`: same fixture with each of the four source types â†’ all rejoin

### Implementation for User Story 2

- [X] T016 [US2] Implement `CorpusCleaner._dehyphenate(text: str, doc_name: str) -> tuple[str, int]` in `packages/rag/rag/knowledge/cleaner.py`: apply `re.sub(r'([a-zA-Z])-\n([a-zA-Z])', r'\1\2', text)`, count matches via `re.findall` before substitution, log at WARNING with count per contract format (`"[corpus-cleaner] Rejoined {N} hyphenated line-breaks in '{doc_name}'"`) if count > 0, return (modified_text, count)
- [X] T017 [US2] Wire `_dehyphenate()` into `CorpusCleaner.clean_pages()` in `packages/rag/rag/knowledge/cleaner.py`: after all page-level rules and after pages are joined with `"\n\n".join(...)`, call `_dehyphenate(joined_text, doc_name)` when `profile.dehyphenation` is True; update `report.hyphens_rejoined`

**Checkpoint**: `test_cleaner.py` US2 tests all pass. Locate a hyphenated term in raw pymupdf4llm output from a rulebook PDF, ingest with cleaning enabled, query the natural form â€” chunk is retrieved.

---

## Phase 5: User Story 3 â€” Chunker Receives Clean Heading Signal (Priority: P2)

**Goal**: TOC sections and front matter pages are stripped before the chunker receives the text.
Every heading in the chunked output represents a real content section. The agentic chunker
no longer produces `"Chapter 3 â€” Disciplines ......... 47"` micro-chunks.

**Independent Test**: `uv run pytest packages/rag/tests/knowledge/test_cleaner.py -k "toc or frontmatter" -v`

### Tests for User Story 3

> **Write these first â€” they MUST FAIL before T019â€“T021**

- [X] T018 [US3] Write failing tests for TOC and front matter rules in `packages/rag/tests/knowledge/test_cleaner.py`:
  - `test_toc_block_stripped`: fixture with 8 lines matching `^.{1,100}[.\s]{2,}\s*\d+\s*$` on page 2 â†’ all 8 lines removed; `report.toc_lines_removed == 8`
  - `test_toc_heading_stripped_with_block`: preceding `## Contents` heading + 6 TOC lines â†’ heading and all 6 lines removed
  - `test_toc_short_list_preserved`: only 3 dot-leader lines â†’ not stripped; `report.toc_lines_removed == 0`
  - `test_toc_scoped_to_early_pages`: fixture with 6 TOC-like lines on page 25 (beyond scope threshold of 20) â†’ preserved unchanged
  - `test_frontmatter_copyright_page_stripped`: page 0 text containing `Copyright Â© 2019` â†’ page removed; `report.frontmatter_pages_removed == 1`
  - `test_frontmatter_dedication_stripped`: page 1 text starting `Dedicated to` â†’ page removed
  - `test_frontmatter_beyond_threshold_preserved`: copyright text on page 12 (beyond default threshold of 10) â†’ page preserved unchanged
  - `test_frontmatter_title_only_stripped`: page 0 with only heading lines (< 20 words total) â†’ stripped
  - `test_source_type_novel_no_toc_rule`: TOC fixture with `source_type="novel"` â†’ lines preserved; `report.toc_lines_removed == 0`
  - `test_source_type_handwritten_no_frontmatter`: copyright page with `source_type="handwritten"` â†’ page preserved
  - `test_bypass_env_var`: `KNOWLEDGE_CLEANING_ENABLED=false` â†’ raw join, no transformations, all report counters at 0

### Implementation for User Story 3

- [X] T019 [US3] Implement `CorpusCleaner._strip_toc(pages: list[PageText], doc_name: str, scope_pages: int) -> tuple[list[PageText], int]` in `packages/rag/rag/knowledge/cleaner.py`: scan only pages with `page_num < scope_pages` (default `KNOWLEDGE_CLEANING_FRONTMATTER_PAGES + 10 = 20`); for each page text, detect a contiguous block of â‰¥ 5 lines matching `r'^.{1,100}[.\s]{2,}\s*\d+\s*$'` or `r'^.{1,100}\t\d+\s*$'`; also strip any immediately-preceding heading line matching `Table of Contents|Contents|TOC` (case-insensitive); remove all matched lines and log at WARNING per contract format; return (modified_pages, total_lines_removed)
- [X] T020 [US3] Implement `CorpusCleaner._strip_frontmatter(pages: list[PageText], doc_name: str, threshold: int) -> tuple[list[PageText], int]` in `packages/rag/rag/knowledge/cleaner.py`: for each page with `page_num < threshold` (default 10), apply patterns: copyright block (`Â©` or line starting `Copyright` or `All rights reserved`), dedication block (`Dedicated to`, `For ` at sentence start, `In memory of`), publisher/ISBN block (`ISBN`, `Printed in`), title-only page (only heading lines, < 20 total words); remove entire page and log at WARNING per contract format; return (filtered_pages, removed_count)
- [X] T021 [US3] Wire TOC and front matter rules into `CorpusCleaner.clean_pages()` in `packages/rag/rag/knowledge/cleaner.py`: apply page-level rules before the join step â€” call `_strip_frontmatter()` when `profile.frontmatter_stripping` is True; call `_strip_toc()` when `profile.toc_stripping` is True; update `report.frontmatter_pages_removed` and `report.toc_lines_removed`; raise `ValueError` for empty `pages` input; pass `doc_name` through from caller; add `doc_name: str = ""` param to `clean_pages()` and `clean_text()` signatures (non-breaking, keyword-only)

**Checkpoint**: `test_cleaner.py` US3 tests all pass. Ingest a rulebook PDF, inspect ChromaDB â€” no chunk contains exclusively TOC dot-leader lines or copyright text.

---

## Phase 6: Polish & Validation

**Purpose**: Verify the player upload form, lint all changed files, run unit tests, and confirm
the gold standard harness meets SC-003 and SC-004.

- [X] T022 Inspect `apps/web/pages/player/knowledge_qa.py` for a document upload form; if one exists, add `source_type_dd = gr.Dropdown(...)` with identical choices, default, and wiring as the GM page in T009; if no upload form exists, add a code comment noting it was checked
- [X] T023 [P] Run `uv run ruff check packages/rag/rag/knowledge/cleaner.py packages/rag/rag/knowledge/ingestor.py packages/rag/rag/knowledge/pipeline.py packages/core/core/models.py apps/web/services/knowledge.py apps/web/pages/gm/knowledge_qa.py` and `uv run pyright` on the same files; fix all errors and warnings
- [X] T024 [P] Run `uv run pytest packages/rag/tests/knowledge/test_cleaner.py -v` and confirm every test passes; fix any failures
- [X] T025 Run bypass regression: `KNOWLEDGE_CLEANING_ENABLED=false uv run pytest packages/rag/tests/ -v`; confirm all tests pass and no regressions in chunking behaviour
- [X] T026 Clear ChromaDB store (rename or delete `./chroma_data`), re-ingest the full corpus with `source_type="rulebook"` and `KNOWLEDGE_CLEANING_ENABLED=true`; verify WARNING log lines appear for each transformation type during ingestion
- [X] T027 Run gold standard: `uv run pytest harness/knowledge_qa/test_gold_standard.py -v -s`; append a new row to `harness/knowledge_qa/benchmark_results.jsonl` with `strategy="agentic+cleaning"`, actual MRR/nDCG/Recall@10 scores, and notes; confirm MRR â‰¥ 0.5767 and Recall@10 â‰¥ 0.8966 (SC-003) and at least one metric strictly above baseline (SC-004)

**Checkpoint**: All unit tests pass. Ruff + pyright clean. Gold standard meets SC-003/SC-004. Bypass regression passes. Feature is complete.

---

## Phase 7: Decision 10 — Structured Output for AgenticChunker

**Goal**: Eliminate the three `"Failed to parse LLM batch response"` WARNING logs by replacing the
manual JSON parse block in `AgenticChunker._chunk_batch()` with a typed `generate_structured()`
call. `OllamaProvider` adds `response_format: json_object` so the sampler cannot produce invalid
JSON. Parse failures downgrade from WARNING to DEBUG.

**Contracts**: [contracts/llm-structured-output.md](contracts/llm-structured-output.md)

**Independent Test**: Run the app and ingest any document — confirm zero `"Failed to parse LLM batch response"` lines appear in the WARNING log. Run `uv run ruff check` + `uv run pyright` clean on the three changed files.

- [X] T028 [P] Define `_ChunkBoundary(BaseModel)` and `_ChunkBoundaryResponse(BaseModel)` at module level in `packages/rag/rag/knowledge/chunker_agentic.py` (before the `AgenticChunker` class): `_ChunkBoundary` has `section: int` and `start_sentence: int`; `_ChunkBoundaryResponse` has `chunks: list[_ChunkBoundary]`; add `from pydantic import BaseModel, ValidationError` to imports
- [X] T029 [P] Add non-abstract `generate_structured(self, prompt: str, response_type: type[T], system: str = "") -> T` to `LLMProvider` in `packages/llm/llm/interface.py`: add `from typing import TypeVar` and `from pydantic import BaseModel` imports; add `T = TypeVar("T", bound=BaseModel)` at module level; implement default body: `raw = await self.generate(prompt=prompt, system=system); return response_type.model_validate_json(raw)`
- [X] T030 [P] Override `generate_structured()` in `OllamaProvider` in `packages/llm/llm/providers/ollama.py`: build `messages` list same as `generate()`; add `"response_format": {"type": "json_object"}` to payload; POST to `/v1/chat/completions`; return `response_type.model_validate_json(raw)`; add `from typing import TypeVar`, `from pydantic import BaseModel` imports and `T = TypeVar("T", bound=BaseModel)` at module level; wrap in same `httpx` error handling as `generate()`
- [X] T031 Replace the manual JSON parse block in `AgenticChunker._chunk_batch()` in `packages/rag/rag/knowledge/chunker_agentic.py` (lines ~179–218): (1) remove the `llm.generate()` call and its surrounding try/except; (2) remove the `cleaned`/fence-stripping/`json.loads()` block and its `except (json.JSONDecodeError, ...)` WARNING; (3) replace both with a single `try: result = await llm.generate_structured(prompt=prompt, response_type=_ChunkBoundaryResponse, system=_SYSTEM_PROMPT) except ValidationError as exc: _log.debug("Structured response did not match schema (sections=%d): %s — one chunk per section", len(sections), exc); return list(sections)`; (4) update `boundary_set` to `{(e.section, e.start_sentence) for e in result.chunks}`; (5) keep the outer `ProviderUnavailableError` re-raise; (6) remove `import json` from module-level imports
- [X] T032 [P] Run `uv run ruff check packages/llm/llm/interface.py packages/llm/llm/providers/ollama.py packages/rag/rag/knowledge/chunker_agentic.py` and `uv run pyright` on the same three files; fix all reported errors and warnings
- [X] T033 Start the app (`uv run python apps/web/app.py`), ingest one document with `source_type="rulebook"`, confirm zero `"Failed to parse LLM batch response"` WARNING lines appear in the log; confirm the chunker still produces chunks (non-empty ingestion)

**Checkpoint**: Three files changed. No WARNING log from `_chunk_batch` during normal ingestion. Ruff + pyright clean. `json` import removed from `chunker_agentic.py`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies â€” start immediately; T002 and T003 parallel with T001
- **Foundational (Phase 2)**: Requires Phase 1 complete
  - T004 and T005 can run in parallel (different packages, no shared import)
  - T006 requires T004 (imports `PageText` from cleaner)
  - T007 requires T006 (calls updated ingestor signatures)
  - T008 requires T007 (calls updated `pipeline.run(source_type=...)`)
  - T009 requires T008 (calls updated `submit_document(source_type=...)`)
- **User Story Phases (3â€“5)**: All require Phase 2 complete; can proceed in priority order
- **Polish (Phase 6)**: Requires all desired user story phases complete
- **Structured Output (Phase 7)**: Independent of Phases 1–6 — touches only `llm/` and `chunker_agentic.py`; T028–T030 run in parallel; T031 requires T028 + T029 + T030; T032–T033 require T031

### User Story Dependencies

- **US1 (P1)**: No dependency on US2 or US3 â€” implements multi-column, stat block, creature blocks
- **US2 (P1)**: No dependency on US1 â€” de-hyphenation is a standalone post-join rule
- **US3 (P2)**: No dependency on US1 or US2 â€” TOC/front matter operate on page-level before join

### Within Each User Story

- Tests MUST be written and FAIL before corresponding implementation tasks
- Private methods implemented before wiring into `clean_pages()` dispatch
- Wiring task validates that test suite turns green

### Parallel Opportunities

| Parallel group | Tasks | Reason |
|----------------|-------|--------|
| Phase 1 | T002, T003 alongside T001 | Different files, no imports |
| Phase 2 row A | T004 â€– T005 | Different packages |
| Phase 2 row B | T007 â€– (nothing) | Sequential after T006 |
| Phase 2 row C | T008, T009 after T007 | T008 first, then T009 |
| Phase 3 impl | T011 â€– T012 | `ingestor.py` â€– `cleaner.py` |
| Phase 6 | T023 â€– T024 | lint â€– unit tests â€” different operations |
| Phase 7 | T028, T029, T030 | different files (chunker_agentic.py, interface.py, ollama.py) |

---

## Parallel Example: User Story 1

```bash
# After T010 tests are written and confirmed failing:

# T011 and T012 run in parallel (different files):
Task: "Implement fitz multi-column extraction in packages/rag/rag/knowledge/ingestor.py"
Task: "Implement stat block reconstruction in packages/rag/rag/knowledge/cleaner.py"

# Then sequentially:
Task: T013 "Creature block preservation (same file as T012)"
Task: T014 "Wire all US1 rules into clean_pages() and ingest_async()"
```

---

## Implementation Strategy

### MVP First (User Story 1 + 2 Only)

US1 and US2 are both P1 and deliver the most retrieval-quality impact:

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (**CRITICAL** â€” blocks all stories)
3. Complete Phase 3: US1 (structured layouts)
4. Complete Phase 4: US2 (de-hyphenation)
5. **STOP and VALIDATE**: run gold standard harness, verify SC-003/SC-004 are met
6. Ship US3 (Phase 5) if time permits

### Incremental Delivery

1. Setup + Foundational â†’ pipeline wired end-to-end, no transformations yet
2. US1 complete â†’ stat blocks and multi-column tables reconstructed
3. US2 complete â†’ all prose searchable without hyphenation artifacts
4. US3 complete â†’ chunker receives clean heading signal, no TOC/front matter noise
5. Polish + gold standard â†’ feature confirmed against baseline

---

## Notes

- `[P]` means different files and no code dependency on an incomplete task
- Test tasks must be written first and confirmed failing before the implementation task starts
- `CorpusCleaner` is stateless and thread-safe by design â€” no shared mutable state
- All transformations follow the logging contract: `"[corpus-cleaner] {transformation} in '{doc_name}': {detail}"`
- The `doc_name` parameter flows from the ingestor caller into `clean_pages(doc_name=...)`; the cleaner itself does not read the file path
- If `KNOWLEDGE_CLEANING_ENABLED=false`, the bypass is in `_extract_chunks()` â€” the cleaner is never instantiated
- fitz is a transitive dep of pymupdf4llm â€” no new dependency is introduced
- Commit after each task or logical group; each phase checkpoint is a good commit boundary
- Phase 7 is independent of Phases 1–6 and can be done in any order; T028–T030 run in parallel then T031 wires them together
