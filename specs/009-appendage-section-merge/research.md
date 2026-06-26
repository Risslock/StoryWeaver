# Research: Appendage Section Merging

**Feature**: 009-appendage-section-merge
**Date**: 2026-06-26

---

## Decision 1 — Where in the pipeline to merge

**Decision**: Merge appendage sections in `AgenticChunker.async_chunk()`, immediately after `HeadingChunker.split_by_headings()` returns and before the LLM batch loop begins.

**Rationale**: Merging before LLM batching means the model sees the full merged context (race description + stat block together) and can make better proposition-boundary decisions. Merging after chunking is too late — the LLM has already produced boundaries without knowing the subject. Merging inside the cleaner (by demoting headings) would prevent the split from ever happening, but risks losing valid heading boundaries in other contexts and couples book-structure knowledge to the cleaner.

**Alternatives considered**:
- Post-chunk merge (after `_enforce_table_atomicity`): Loses LLM context benefit; stat block still separated during LLM call.
- Cleaner-level heading demotion: Changes `##` to `**bold**` for detected appendage headings. Non-generalizable without knowing which headings to demote; couples the cleaner to chunking concerns.
- Keyword-based heading blacklist: Hard-coded list of heading names ("Game Information", "Starting Attribute Values"). Breaks on every new book.

---

## Decision 2 — Prose density as the detection signal

**Decision**: Classify a section as an appendage when fewer than `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD` (default 0.3) of its content lines are prose lines.

**Rationale**: The structural difference between an appendage and a self-contained section is observable in word count per line. Stat block lines ("DEX 11", "Movement Rate: 12", "| DEX | 11 |") are short data entries. Prose sections contain full sentences. The threshold of 0.3 creates a clean separation in practice: ED4 stat block sections land at 0–5% prose; sections with even one explanatory sentence land at 40–100%.

**Alternatives considered**:
- Fixed minimum line count: Too fragile — a long stat table would pass, a very short prose paragraph would fail.
- Embedding similarity to previous section: Correct in principle but adds an embedding call per section pair, negating the LLM-skipping optimization from the prior session.
- NLP sentence parser (spaCy, NLTK): Accurate but adds a heavyweight dependency for a heuristic.

---

## Decision 3 — Prose line definition

**Decision**: A line is "prose" if it has ≥ 8 whitespace-separated tokens AND does not start with `#` (heading) or `|` (table row).

**Rationale**: 8 tokens is a reliable lower bound for a grammatical English sentence. Lines with fewer tokens are almost always data labels, values, or cross-references. Heading lines and table rows are excluded from both the prose count and the denominator so they don't dilute the ratio.

**Edge cases resolved**:
- A heading-only section (no content lines after the `#` line): denominator = 0 → classified as appendage (handled by explicit check, not division).
- A line like "DEX 11, STR 10, TOU 11, PER 10, WIL 10, CHA 11" has 9 tokens but is data. After `CorpusCleaner` stat block reconstruction, this becomes a table row (`| DEX | 11 |`) and is excluded from prose count. If the raw line survives, 9 tokens still lands under a reasonable prose sentence length given the pattern — acceptable false negative at worst.
- Table rows with many words (e.g., a descriptive table cell): excluded from prose count because they start with `|`. This is correct — table cells should not rescue a data-heavy section.

---

## Decision 4 — Size cap for merging

**Decision**: Only merge when `estimate_tokens(preceding) + estimate_tokens(appendage) <= max_tokens * 4`.

**Rationale**: `max_tokens * 4` is already the cap used by `HeadingChunker` when it creates sections to hand off to `AgenticChunker`. Reusing the same constant keeps behaviour consistent: a merged section will never exceed what the `HeadingChunker` would have produced for a very large single section. When the cap would be exceeded, the appendage is emitted standalone — it is still retrievable, just without parent context.

---

## Decision 5 — Environment variable naming

**Decision**: `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD` (float, default `0.3`).

**Rationale**: Follows the existing `KNOWLEDGE_AGENTIC_*` prefix convention (`KNOWLEDGE_AGENTIC_BATCH_SECTIONS`, `KNOWLEDGE_AGENTIC_SKIP_TOKENS`). Stored as a float so values like `0.25` or `0.5` are expressible without ambiguity.

---

## Decision 6 — Logging

**Decision**: Log each merge at `INFO` level (Constitution VIII), including the first line of the appendage section (truncated to 80 chars) and the prose ratio.

**Rationale**: INFO is the appropriate level for significant pipeline events visible in normal operation. Including the first line of the merged section provides traceability without flooding the log. The prose ratio in the message allows a developer to understand why a section was classified as an appendage.

---

## Summary of resolved unknowns

| Unknown | Resolution |
|---|---|
| Where to insert the merge step | `AgenticChunker.async_chunk()` before LLM batch loop |
| Detection signal | Prose ratio < threshold (default 0.3) |
| Prose line definition | ≥8 tokens, non-heading, non-table |
| Heading-only sections | Always appendage (explicit check) |
| Size guard | `max_tokens * 4`, same as HeadingChunker cap |
| Env var name | `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD` |
| Log level | INFO |
