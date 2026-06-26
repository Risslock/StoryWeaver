# Implementation Plan: Appendage Section Merging via Prose Density

**Branch**: `009-appendage-section-merge` | **Date**: 2026-06-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-appendage-section-merge/spec.md`

## Summary

Structured-data sections (stat blocks, attribute tables) are split from their parent sections by `HeadingChunker`, causing them to lose their subject context when retrieved as RAG chunks. The fix is a prose-density heuristic applied in `AgenticChunker.async_chunk()` immediately after `split_by_headings()`: sections where fewer than 30% of non-heading, non-table lines have ≥8 words are merged into the preceding section before LLM batching, so the model sees the full context. The threshold is configurable via `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD`.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `packages/rag` — `rag.knowledge.chunker_agentic.AgenticChunker`, `rag.knowledge.chunker.HeadingChunker`, `rag.knowledge.chunker.estimate_tokens`

**Storage**: N/A — in-memory pipeline transform only

**Testing**: `pytest` — new unit tests in `packages/rag/tests/knowledge/test_chunker_agentic.py`

**Target Platform**: Local (Ollama), same as existing chunker stack

**Project Type**: Library — internal pipeline component within `packages/rag`

**Performance Goals**: The merge step is O(n) over section count with no I/O; negligible overhead relative to LLM call latency.

**Constraints**: Must not alter `HeadingChunker` or `SemanticChunker` behaviour. Must not increase peak memory. Combined merged section must not exceed `max_tokens * 4`.

**Scale/Scope**: Per-document ingestion; a 500-page rulebook produces ~hundreds of sections.

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. Spec-Driven | ✅ | spec.md written before implementation |
| II. Provider Abstraction | ✅ | No new providers; works with existing LLM abstraction |
| III. Package Isolation | ✅ | Change confined to `packages/rag`; no new packages |
| IV. Local-First | ✅ | Pure Python, no cloud dependency |
| V. Harness-Driven Quality | ⚠️ | Unit tests required (see tasks); harness eval deferred — acceptable since merging logic is deterministic, not agentic |
| VI. Product-First | ✅ | Directly improves RAG answer quality for stat block context |
| VII. Placeholder-First | N/A | Internal pipeline step; no UI surface |
| VIII. Structured Logging | ✅ | INFO log per merge, `logging.getLogger(__name__)`, no bare print |

**Gate**: ✅ Pass. Harness eval deferred with justification (deterministic heuristic; unit tests provide sufficient coverage per Constitution V exception for non-agentic logic).

## Project Structure

### Documentation (this feature)

```text
specs/009-appendage-section-merge/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions and rationale
├── data-model.md        # Phase 1 — computational entities and pipeline position
├── quickstart.md        # Phase 1 — validation scenarios
└── tasks.md             # Phase 2 — /speckit-tasks output
```

### Source Code

```text
packages/rag/
├── rag/knowledge/
│   └── chunker_agentic.py     # _prose_ratio(), _merge_appendage_sections(), __init__ update
└── tests/knowledge/
    └── test_chunker_agentic.py  # new appendage / merge / size_cap test cases

.env                             # add KNOWLEDGE_AGENTIC_PROSE_THRESHOLD=0.3
.env.example                     # same, with explanatory comment
```

**Structure Decision**: Single-package change. All logic is confined to `chunker_agentic.py`. No new files outside `packages/rag` and env configuration.

## Design Decisions

See [research.md](research.md) for full rationale. Summary:

| Decision | Choice |
|---|---|
| Pipeline position | Before LLM batch loop in `async_chunk()` |
| Detection signal | Prose ratio (prose lines / content lines) |
| Prose line definition | ≥8 whitespace-separated tokens, non-heading, non-table |
| Heading-only section | Always appendage (explicit check, avoids divide-by-zero) |
| Size guard | `max_tokens * 4` — same cap as `HeadingChunker` section limit |
| Env var | `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD` (float, default `0.3`) |
| Logging | `INFO` per merge; includes first line (truncated) and prose ratio |

## Implementation Notes

### `_prose_ratio(section: str) -> float` — module-level pure function

Strips heading lines (`startswith("#")`) and table rows (`startswith("|")`) from the section, then returns `prose_count / content_count` where prose lines have `len(line.split()) >= 8`. Returns `0.0` when no content lines exist.

### `AgenticChunker._merge_appendage_sections(sections)` — instance method

Iterates sections in order. For each section:
- If `_prose_ratio(section) < self._prose_threshold` OR section has no content lines → appendage
- If appendage and preceding exists and combined tokens ≤ `max_tokens * 4` → merge
- If appendage and cap exceeded → emit standalone + INFO log
- Otherwise → emit as-is

### `AgenticChunker.__init__` addition

```python
self._prose_threshold = prose_threshold or float(
    os.environ.get("KNOWLEDGE_AGENTIC_PROSE_THRESHOLD", "0.3")
)
```

### Call site in `async_chunk()`

```python
sections = heading_chunker.split_by_headings(text)
if not sections:
    sections = [text]
sections = self._merge_appendage_sections(sections)  # ← new line
# existing fast-path and LLM batch loop unchanged
```
