# Feature Specification: Appendage Section Merging via Prose Density

**Feature Branch**: `009-appendage-section-merge`

**Created**: 2026-06-26

**Status**: Draft

**Input**: User description: "When a PDF rulebook is split into heading-based sections, structured-data sections (stat blocks, attribute tables, equipment lists, game info blocks) become isolated chunks that lose the context of their parent section. The chunker needs to detect and merge these appendage sections back into the preceding section before LLM batching, using prose density as the signal — no hard-coded heading names."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stat Blocks Retain Entity Context (Priority: P1)

A GM ingests an Earthdawn rulebook. After ingestion, when the RAG system retrieves a chunk about a race's attributes (e.g. DEX 11, STR 10, Movement Rate 12), the chunk also contains the race name and description — so the answer is grounded in the correct entity without requiring extra metadata injection.

**Why this priority**: The core problem being solved. Without this, retrieved stat blocks are useless because they contain numbers with no subject.

**Independent Test**: Ingest a rulebook section containing a race entry with a "Game Information" block. Query for that race's DEX value. The returned chunk must contain both the race name and the attribute value in the same chunk.

**Acceptance Scenarios**:

1. **Given** a PDF with a T'skrang race section followed by a "Game Information" heading and attribute lines, **When** the document is ingested, **Then** the resulting chunks contain at least one chunk that includes both "T'skrang" and "DEX" in its text.
2. **Given** a "Game Information" section consisting entirely of key:value attribute lines, **When** it is processed by the chunker, **Then** it is merged into the preceding race-description section rather than emitted as a standalone chunk.
3. **Given** a structured-data section whose merge would exceed the size cap, **When** it is processed, **Then** it is left as a separate chunk rather than producing an oversized merged chunk.

---

### User Story 2 - Generalization Across Books Without Configuration (Priority: P2)

A GM ingests a second Earthdawn sourcebook with different heading structures (e.g. "Creature Statistics", "Discipline Abilities", "Starting Values"). The appendage merging works correctly without adding any book-specific rules or heading name lists.

**Why this priority**: Hard-coded heading lists break with every new book. The value of this feature is that it requires zero per-book configuration.

**Independent Test**: Ingest a second source document that uses different heading names for its structured-data blocks. Verify that stat-block-like sections are merged and prose sections are not, solely based on content density.

**Acceptance Scenarios**:

1. **Given** a section whose heading name does not appear in any configured list, **When** its content is less than 30% prose lines, **Then** it is merged with the preceding section.
2. **Given** a section with a heading like "Racial Abilities" that contains full prose sentences describing an ability, **When** processed, **Then** it is NOT merged (prose density is above the threshold).
3. **Given** a heading-only section (heading present, no content below it), **When** processed, **Then** it is always merged with the preceding section.

---

### User Story 3 - Threshold Tuning Without Code Changes (Priority: P3)

A developer evaluating ingestion quality can raise or lower the prose density threshold via an environment variable and re-run ingestion to compare results — without touching any code.

**Why this priority**: The 30% default is a starting point. Different corpora may need different calibration, and making it configurable enables systematic evaluation.

**Independent Test**: Set `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD` to 0.5, ingest a document, observe that more sections are merged than at 0.3. Reset to 0.1 and observe fewer merges. No code changes required between runs.

**Acceptance Scenarios**:

1. **Given** `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD=0.5`, **When** a section with 40% prose lines is encountered, **Then** it is treated as an appendage and merged.
2. **Given** `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD=0.1`, **When** the same section is encountered, **Then** it is NOT merged (40% > 10%).
3. **Given** the env var is absent, **When** the chunker runs, **Then** the default threshold of 0.3 is applied.

---

### Edge Cases

- What happens when the first section in a document is a data-only block (no preceding section to merge into)? It must be emitted as-is rather than dropped.
- What happens when two consecutive appendage sections follow a prose section? Both should be merged sequentially into the growing preceding section, as long as the size cap is not exceeded.
- What if a table row has more than 8 words? Table lines (starting with `|`) must be excluded from the prose count regardless of word count.
- What if the entire document consists of structured data with no prose sections? All sections should pass through unchanged (no preceding section to merge into for the first one; subsequent ones merge into the result of the prior merge).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The chunker MUST detect "appendage" sections — heading sections whose non-heading, non-table content lines are less than a configurable prose threshold — before LLM batching.
- **FR-002**: Detection MUST be based solely on content characteristics (word count per line, line type) with no hard-coded heading names, keywords, or book-specific patterns.
- **FR-003**: A section with no content below its heading (heading-only) MUST always be classified as an appendage.
- **FR-004**: Table lines (lines starting with `|`) MUST be excluded from both the prose count and the total content line count used for the density ratio.
- **FR-005**: An appendage section MUST be merged into the immediately preceding section when the combined token count does not exceed `max_tokens × 4`.
- **FR-006**: When the size cap would be exceeded, the appendage MUST be emitted as a standalone section rather than dropped or truncated.
- **FR-007**: The prose density threshold MUST be configurable via the `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD` environment variable, defaulting to `0.3`.
- **FR-008**: The merging step MUST run before LLM batch construction so the LLM sees the merged context.
- **FR-009**: Each merge event MUST be logged at `INFO` level, identifying the first line of the appendage section that was merged.
- **FR-010**: The feature MUST NOT alter behavior of the `HeadingChunker` or `SemanticChunker` strategies — it applies only within `AgenticChunker`.

### Key Entities

- **Appendage Section**: A heading-delimited text block whose content is predominantly structured data. Defined by prose ratio below threshold. Has no standalone meaning without the preceding section.
- **Prose Ratio**: The fraction of a section's content lines (excluding heading lines and table rows) that contain 8 or more words. The signal used to classify a section as appendage or self-contained.
- **Size Cap**: `max_tokens × 4` — the same upper bound used by `HeadingChunker` for individual sections. Prevents merged sections from being too large for the LLM context.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After ingestion of any Earthdawn rulebook, every chunk containing race or creature attribute values also contains the entity name in the same chunk — verified by searching for attribute keywords and checking for an accompanying proper noun.
- **SC-002**: Zero prose-only sections (those with ≥ 30% prose lines at the default threshold) are incorrectly merged into a preceding section.
- **SC-003**: The merging logic produces correct output across at least two different Earthdawn source books without any book-specific configuration changes.
- **SC-004**: Changing `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD` takes effect on the next ingestion run with no code changes and no service restart.
- **SC-005**: Merged sections are visible in the INFO-level logs, allowing a developer to verify which appendages were detected during any ingestion run.

## Assumptions

- The Markdown produced by pymupdf4llm uses `#`, `##`, or `###` heading markers — the same set that `HeadingChunker.split_by_headings` already splits on.
- A "prose sentence" is approximated as any non-heading, non-table line with 8 or more whitespace-separated tokens. This is a fast heuristic, not a full sentence parser.
- The 30% default threshold was calibrated against Earthdawn 4E Player's Guide stat blocks; other corpora may require adjustment via the env var.
- The stat block cleaner in `CorpusCleaner` may convert raw attribute lines into Markdown tables (`| Attribute | Value |`) before this step runs. The prose density check correctly handles both raw lines and table rows by excluding `|`-prefixed lines.
- Documents may have both prose-heavy and data-heavy sub-sections under the same parent heading; only the data-heavy ones are merged.
