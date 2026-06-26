# Tasks: Appendage Section Merging via Prose Density

**Input**: Design documents from `specs/009-appendage-section-merge/`

**Organization**: Tasks are grouped by user story. Each phase is independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different concerns, no unresolved dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup

**Purpose**: Add environment variable configuration for the new threshold.

- [X] T001 Add `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD=0.3` to `.env` with comment explaining that sections below this prose ratio are merged into the preceding section
- [X] T002 [P] Add `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD=0.3` to `.env.example` with the same comment

---

## Phase 2: Foundational (Blocking Prerequisite)

**Purpose**: The `_prose_ratio()` pure function is used by all user story phases and must exist before any merge logic is written.

**⚠️ CRITICAL**: T003 must be complete before Phase 3 can begin.

- [X] T003 Add module-level pure function `_prose_ratio(section: str) -> float` to `packages/rag/rag/knowledge/chunker_agentic.py` — splits section into lines, filters out heading lines (starting with `#`) and table rows (starting with `|`), counts lines with ≥8 whitespace-separated tokens as prose, returns `prose / total_content` or `0.0` when no content lines exist

**Checkpoint**: `_prose_ratio` is callable and returns a float for any string input.

---

## Phase 3: User Story 1 — Stat Blocks Retain Entity Context (P1) 🎯 MVP

**Goal**: After ingestion, every chunk containing race/creature attribute values also contains the entity name in the same text block.

**Independent Test**: Ingest a document section containing a race description followed by a "Game Information" heading with attribute lines. Query for a stat value. The returned chunk must include both the entity name and the attribute value.

### Implementation

- [X] T004 [US1] Add `prose_threshold: float | None = None` parameter to `AgenticChunker.__init__()` and store as `self._prose_threshold = prose_threshold or float(os.environ.get("KNOWLEDGE_AGENTIC_PROSE_THRESHOLD", "0.3"))` in `packages/rag/rag/knowledge/chunker_agentic.py`
- [X] T005 [US1] Implement `_merge_appendage_sections(self, sections: list[str]) -> list[str]` in `packages/rag/rag/knowledge/chunker_agentic.py` — iterates sections in order; classifies each as appendage when `_prose_ratio(section) < self._prose_threshold` or section has no content lines; merges into preceding section when combined token count ≤ `self._max_tokens * 4`; emits standalone when size cap would be exceeded; logs each merge at INFO with prose ratio and first line (truncated to 80 chars); logs cap-exceeded skip at INFO
- [X] T006 [US1] Insert `sections = self._merge_appendage_sections(sections)` in `async_chunk()` immediately after the `if not sections: sections = [text]` guard and before the fast-path/LLM batch loop in `packages/rag/rag/knowledge/chunker_agentic.py`

### Tests for User Story 1

- [X] T007 [P] [US1] Write unit test in `packages/rag/tests/knowledge/test_chunker_agentic.py`: `_prose_ratio()` returns 0.0 for a section where all content lines have ≤7 words (e.g. `"## Game Information\nDEX: 11\nSTR: 10\nMovement Rate: 12"`)
- [X] T008 [P] [US1] Write unit test in `packages/rag/tests/knowledge/test_chunker_agentic.py`: `_prose_ratio()` returns a value ≥ 0.5 for a section containing multiple full prose sentences (≥8 words each)
- [X] T009 [P] [US1] Write unit test in `packages/rag/tests/knowledge/test_chunker_agentic.py`: heading-only section (heading line + no content below) is classified as appendage (prose ratio treated as 0.0)
- [X] T010 [P] [US1] Write unit test in `packages/rag/tests/knowledge/test_chunker_agentic.py`: table rows (`| DEX | 11 |`) are excluded from both prose count and denominator so a section of only table rows has prose ratio 0.0
- [X] T011 [US1] Write unit test in `packages/rag/tests/knowledge/test_chunker_agentic.py`: `_merge_appendage_sections()` merges a low-prose stat block section into the preceding prose-heavy race description; the merged result contains both the race name and an attribute keyword
- [X] T012 [US1] Write unit test in `packages/rag/tests/knowledge/test_chunker_agentic.py`: when the first section in the list is an appendage (no preceding section), it is emitted as-is rather than dropped
- [X] T013 [US1] Write unit test in `packages/rag/tests/knowledge/test_chunker_agentic.py`: when merging an appendage would exceed `max_tokens * 4`, the appendage is emitted as a standalone section and the preceding section is unchanged

**Checkpoint**: `pytest packages/rag/tests/knowledge/test_chunker_agentic.py -k "prose_ratio or merge or appendage or size_cap"` passes. A race description + stat block pair produces a single merged chunk in `async_chunk()` output.

---

## Phase 4: User Story 2 — Generalization Across Books (P2)

**Goal**: The detection logic works on any heading name and any book structure using only content characteristics.

**Independent Test**: Feed sections with non-ED4 heading names ("Creature Statistics", "Starting Values") to `_merge_appendage_sections()`. Verify merging is driven by line content, not heading text.

### Tests for User Story 2

- [X] T014 [P] [US2] Write unit test in `packages/rag/tests/knowledge/test_chunker_agentic.py`: a section headed `## Creature Statistics` with only short attribute lines is classified as appendage and merged — verifies no heading-name dependency
- [X] T015 [P] [US2] Write unit test in `packages/rag/tests/knowledge/test_chunker_agentic.py`: a section headed `## Racial Abilities` containing multiple full prose sentences (≥8 words each) is NOT merged — prose ratio is above threshold
- [X] T016 [US2] Write unit test in `packages/rag/tests/knowledge/test_chunker_agentic.py`: two consecutive appendage sections following a single prose section are both merged into the growing preceding section (provided size cap is not hit), preserving all attribute data with the parent context

**Checkpoint**: `pytest packages/rag/tests/knowledge/test_chunker_agentic.py -k "generali or book or racial or consecutive"` passes. No heading names appear as string literals in `_merge_appendage_sections()` or `_prose_ratio()`.

---

## Phase 5: User Story 3 — Threshold Tuning Without Code Changes (P3)

**Goal**: A developer can raise or lower `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD` and observe different merge behaviour on the next ingestion run.

**Independent Test**: Monkeypatch `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD` to 0.5, instantiate `AgenticChunker`, confirm a section with 40% prose lines is merged. Reset to 0.1, confirm same section is not merged.

### Tests for User Story 3

- [X] T017 [P] [US3] Write unit test in `packages/rag/tests/knowledge/test_chunker_agentic.py`: `AgenticChunker(prose_threshold=0.5)` merges a section with 40% prose lines (prose ratio 0.4 < 0.5)
- [X] T018 [P] [US3] Write unit test in `packages/rag/tests/knowledge/test_chunker_agentic.py`: `AgenticChunker(prose_threshold=0.1)` does NOT merge the same section with 40% prose lines (prose ratio 0.4 > 0.1)
- [X] T019 [US3] Write unit test in `packages/rag/tests/knowledge/test_chunker_agentic.py`: instantiating `AgenticChunker()` with no arguments and no env var set results in `self._prose_threshold == 0.3`

**Checkpoint**: `pytest packages/rag/tests/knowledge/test_chunker_agentic.py -k "threshold or env"` passes. Threshold change requires no code edit.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Lint, type safety, and end-to-end validation.

- [X] T020 Run `pytest packages/rag/tests/knowledge/test_chunker_agentic.py -v` and confirm all tests pass (including existing tests unrelated to this feature)
- [X] T021 [P] Run `ruff check packages/rag/rag/knowledge/chunker_agentic.py` and resolve any lint issues
- [X] T022 [P] Run `pyright packages/rag/rag/knowledge/chunker_agentic.py` and resolve any type errors (`_prose_ratio` return type, `_merge_appendage_sections` parameter/return types)
- [X] T023 Validate quickstart scenarios 1 and 2 from `specs/009-appendage-section-merge/quickstart.md` (unit-level runs)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — can start immediately
- **Phase 2 (Foundational)**: No dependencies — can start immediately in parallel with Phase 1
- **Phase 3 (US1)**: Requires T003 (Phase 2). T004, T005, T006 are sequential within US1. Tests T007–T010 can start after T003; T011–T013 require T005
- **Phase 4 (US2)**: Requires T005 (merge logic). All US2 tests are independent of each other
- **Phase 5 (US3)**: Requires T004 (`prose_threshold` param). All US3 tests are independent of each other
- **Phase 6 (Polish)**: Requires all prior phases complete

### User Story Dependencies

- **US1 (P1)**: Depends on Foundational (T003) only. Standalone.
- **US2 (P2)**: Depends on US1 merge implementation (T005). Tests verify generalization — no code additions.
- **US3 (P3)**: Depends on US1 `__init__` update (T004). Tests verify env var wiring — no code additions beyond T004.

### Within Phase 3

```
T003 (Foundational) → T004 → T005 → T006
                   ↘ T007, T008, T009, T010 (parallel, after T003)
                              ↘ T011, T012, T013 (after T005)
```

---

## Parallel Opportunities

```bash
# Phase 1 + Phase 2 can run simultaneously:
Task T001  # .env update
Task T002  # .env.example update
Task T003  # _prose_ratio() function

# After T003 completes, within Phase 3 (US1):
Task T007  # test: prose_ratio pure data
Task T008  # test: prose_ratio prose section
Task T009  # test: heading-only
Task T010  # test: table row exclusion

# After T005 completes, US2 tests can run in parallel:
Task T014  # test: non-ED4 heading name
Task T015  # test: prose-heavy sub-section not merged

# After T004 completes, US3 tests can run in parallel:
Task T017  # test: threshold=0.5
Task T018  # test: threshold=0.1

# After all stories complete, in parallel:
Task T021  # ruff
Task T022  # pyright
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1 + Phase 2 (T001–T003)
2. Complete Phase 3 US1 implementation (T004–T006)
3. Complete Phase 3 US1 tests (T007–T013)
4. **STOP and VALIDATE**: run pytest, ingest a sample document, verify entity context is preserved in chunks
5. Ship if retrieval quality is satisfactory

### Incremental Delivery

1. T001–T003: Foundation ready
2. T004–T013 (US1): Core merging works → validate with real PDF
3. T014–T016 (US2): Confirm generalization via tests (no new code)
4. T017–T019 (US3): Confirm threshold tuning via tests (no new code beyond T004)
5. T020–T023: Polish and sign-off

---

## Notes

- No UI changes. No new packages. No new persistent data.
- `_prose_ratio()` is a module-level pure function (not a method) so it can be unit-tested without instantiating `AgenticChunker`.
- US2 and US3 require zero additional production code beyond what US1 introduces — their tasks are test coverage only.
- The `[P]` marker on tests T007–T010 and T014–T015 and T017–T018 means they can be written simultaneously since they target different test functions.
- Commit after T006 (implementation complete), again after T013 (US1 tests green), and after T020 (all tests green).
