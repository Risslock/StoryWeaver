# Feature Specification: Corpus Pre-Processing & Cleaning

**Feature Branch**: `008-corpus-cleaning`

**Created**: 2026-06-25

**Status**: Draft

**Input**: User description: "Corpus Pre-Processing & Cleaning — fix PDF extraction problems upstream of chunking. The multi-source corpus (RPG rulebooks, supplements, handwritten character/story corpus, novels) has several extraction artifacts that pollute the chunking pipeline: complex structured layouts (multi-column tables, stat blocks, creature examples), de-hyphenation, front matter and TOC pollution. The cleaning step should run after PDF-to-Markdown conversion and before the chunker receives the text, but recommendations on the extraction phase itself are also in scope. Scope: pre-processing/cleaning only."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Structured Layouts Retrieved Accurately (Priority: P1)

A GM asks the system a question about a game mechanic defined in a structured block —
for example, "What are the attribute modifiers for a Windling?", "What abilities does a
Horror Stalker have?", or "What is the karma cost for the Mystic Armour talent?" RPG
rulebooks use a wide variety of structured layouts that PDF extraction typically handles
poorly: multi-column tables (2, 3, 4 or more columns), stat blocks (boxed key-value
attribute grids for creatures and characters), creature example blocks (mixing prose
descriptions with embedded stat lines), and complex spell or skill tables.

Standard PDF-to-Markdown conversion reads pages left-to-right, top-to-bottom across the
full page width, producing garbled or interleaved content for any layout that organises
information in columns. The chunker stores this garbled text verbatim, and the retriever
either returns nonsense or misses the question entirely.

After this feature is delivered, structured layouts are reconstructed into coherent
Markdown — whether by improving how the extraction step reads the PDF, by a post-extraction
cleaning pass, or both — so the chunker receives meaningful, correctly ordered content.

**Why this priority**: Earthdawn and similar RPG rulebooks are defined by their structured
content. Races, disciplines, talents, spells, creatures, and items are all described in
tables and stat blocks. If these structures are garbled at extraction, the majority of
rule content is unretrievable regardless of chunking strategy.

**Independent Test**: Ingest a PDF containing at least one multi-column table, one stat
block, and one creature example block. Run gold standard questions whose answers live in
those structures. Confirm retrieved chunks contain correctly ordered, readable content —
not interleaved or shuffled data.

**Acceptance Scenarios**:

1. **Given** a PDF with a multi-column attribute table (e.g., racial modifiers across
   3+ columns), **When** the document is ingested, **Then** the resulting Markdown
   preserves each row in correct column order — values are not interleaved across
   adjacent columns.
2. **Given** a PDF with a creature stat block (a boxed block listing Name, DEX Step,
   STR Step, Initiative, Attacks, etc.), **When** the document is ingested, **Then**
   the stat block is represented as a coherent key-value list or Markdown table — not
   as scrambled lines from a top-to-bottom column read.
3. **Given** a PDF with a creature example block (a worked example combining prose
   description, stat lines, and special ability descriptions), **When** ingested, **Then**
   the block is extracted as a single, self-contained Markdown section — not fragmented
   across unrelated paragraphs.
4. **Given** any of the above structured layout types, **When** the gold standard
   evaluation is run post-ingestion, **Then** retrieval recall for questions whose answers
   are inside those structures improves over the pre-cleaning baseline.

---

### User Story 2 - Rule Text Searchable Without Hyphenation Breaks (Priority: P1)

A GM or player asks the system about "karma" or "step dice" — terms that appear in the
rulebook but are sometimes exported as "kar-\nma" or "step\ndice" due to line-break
hyphenation in the original PDF layout. Queries using the natural form find nothing
because the indexed text contains the broken form.

After this feature is delivered, all hyphenated line-break splits are re-joined before
the text reaches the chunker — whether caught at the extraction step or in a post-extraction
cleaning pass — so every term is indexed in its natural form and discoverable by
natural-language queries.

**Why this priority**: De-hyphenation is pervasive across all PDF-exported books and
affects the indexability of any term that happened to be split at a column or page
boundary. Unlike layout garbling (which affects identifiable structured blocks),
hyphenation breaks are scattered throughout all running prose.

**Independent Test**: Locate a term in the raw extracted Markdown that appears in
hyphenated form. Ingest the PDF with the fix in place and run a query using the natural
(unhyphenated) form. Confirm the chunk containing the formerly-broken term is retrieved.
Then confirm the same query against a corpus ingested without the fix fails to retrieve it.

**Acceptance Scenarios**:

1. **Given** extracted Markdown containing "cha-\nracter" or "tal-\nent", **When**
   the pipeline processes the document, **Then** the text reaching the chunker contains
   "character" and "talent" — no hyphen-newline artifact remains.
2. **Given** a legitimate intentional hyphen not at a line break (e.g., "step-based",
   "one-shot", "half-magic"), **When** the pipeline processes the text, **Then** the
   hyphen is preserved unchanged.
3. **Given** a full PDF ingested with the fix in place, **When** the gold standard
   evaluation runs, **Then** no retrieval misses are attributable to hyphenation artifacts.

---

### User Story 3 - Chunker Receives Clean Heading Signal (Priority: P2)

The agentic chunker uses heading markers (`#`, `##`, `###`) in the Markdown to identify
section boundaries. Two categories of content produce spurious headings that pollute this
signal:

**Table of Contents**: RPG rulebooks typically open with a multi-page TOC listing every
chapter and section title alongside its page number. Extracted to Markdown, these lines
appear as heading-formatted text. The chunker treats each as a real section, producing
tiny meaningless chunks ("Chapter 3 — Disciplines ......... 47") with no game content.

**Front matter**: Title pages, copyright notices, dedications, acknowledgements, and
publisher information appear before the first real content chapter. These carry
heading-level markers but contain no game content.

After this feature is delivered, both categories are stripped (or skipped during
extraction) before the chunker receives the text. Every heading in the chunked output
represents a real content section.

**Why this priority**: TOC and front matter pollution is deterministic and fixable with
pattern-based detection rules. Cleaning it directly improves the heading signal quality
that the agentic chunker relies on, with no risk of content loss when detection bounds
are correctly set.

**Independent Test**: Ingest a PDF with a visible TOC and front matter. Inspect the
chunks in the vector store. Confirm no chunk contains exclusively TOC entry lines
("chapter name + page number" pattern) or front matter text (copyright, dedication).
Query a question whose answer is in a chapter that also appears in the TOC — confirm the
returned chunk is the actual content, not the TOC reference line.

**Acceptance Scenarios**:

1. **Given** a PDF whose first pages are front matter (title, copyright, dedication),
   **When** the document is ingested, **Then** no chunk in the vector store contains
   exclusively front matter text.
2. **Given** a PDF with a Table of Contents, **When** ingested, **Then** no chunk
   contains TOC entry lines (lines matching "section name ... page number" pattern).
3. **Given** a chapter name that appears in both the TOC and as the actual chapter
   heading in the body, **When** the gold standard evaluation is run, **Then** retrieval
   returns the actual chapter content chunk — not the TOC reference line.
4. **Given** a PDF with no TOC or front matter (e.g., a short supplement), **When**
   ingested, **Then** content is preserved exactly unchanged — no legitimate content is
   removed.

---

### Edge Cases

- What if the best fix for a layout problem is to improve the extraction step rather
  than add a post-extraction cleaner? Both approaches are in scope; the research phase
  of this spec MUST evaluate extraction-level improvements and post-extraction cleaning,
  and MAY recommend different approaches for different problem types.
- What happens when a PDF has no multi-column layout or stat blocks? The pipeline MUST
  pass single-column content unchanged — no false-positive restructuring of
  already-correct content.
- What happens when a hyphen at end-of-line is intentional (e.g., a dash in a heading
  or a list marker)? Only the specific pattern `word-\ncontinuation-word` must be merged;
  standalone dashes, em-dashes, list markers, and mid-word hyphens not at a line-end
  MUST be preserved.
- What happens when a PDF has unusually long front matter (e.g., a 20-page introduction
  that reads like real content)? A configurable page threshold (default: first 10 pages)
  MUST bound how far into the document front matter detection is applied. Content beyond
  the threshold MUST be preserved, not silently removed.
- What happens when a stat block or creature example spans a page boundary? The pipeline
  MUST attempt to reconstruct the block across the break; if it cannot, it MUST preserve
  the content as-is and log a WARNING — it MUST NOT drop content.
- What happens when two structured layout types appear on the same page (e.g., a stat
  block next to a multi-column table)? Each MUST be handled independently without the
  rules for one interfering with the other.
- What happens if no known pattern is detected in a section of the document? The pipeline
  MUST pass unrecognised content through unchanged and log a DEBUG note — it MUST NOT
  crash or silently drop content.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: This feature covers the full pre-chunking extraction pipeline — both the
  PDF-to-Markdown conversion step and any post-conversion cleaning pass. The research
  phase MUST evaluate whether improvements belong at the extraction level, the cleaning
  level, or both, and document the rationale for the approach chosen.
- **FR-002**: The pipeline MUST correctly extract or reconstruct multi-column table
  layouts of any column count (2, 3, 4+). Rows MUST be output in correct column order —
  all cells of a row across all columns before moving to the next row.
- **FR-003**: The pipeline MUST correctly extract or reconstruct stat blocks — structured
  key-value attribute grids used for creatures, characters, items, and disciplines.
  Stat blocks MUST be output as coherent Markdown tables or key-value lists.
- **FR-004**: The pipeline MUST correctly extract or preserve creature example blocks —
  composite sections combining prose description, stat lines, and special ability text.
  These MUST appear as contiguous, self-contained sections in the output Markdown.
- **FR-005**: The pipeline MUST re-join hyphenated line-break splits. The rule:
  `<word>-\n<continuation-word>` is merged into `<word><continuation>`. Hyphens not
  immediately followed by a newline and a word character MUST be preserved.
- **FR-006**: Table of Contents sections MUST be stripped before the chunker receives
  the text. A TOC section is identified by a heading or heading-like block followed by
  lines matching "text ... number" or "text\tpage" patterns. The entire TOC section is
  removed.
- **FR-007**: Front matter MUST be stripped up to a configurable page threshold
  (`KNOWLEDGE_CLEANING_FRONTMATTER_PAGES`, default 10). Recognised front matter patterns:
  title-only pages, copyright blocks, dedication blocks, publisher information blocks.
  Content beyond the threshold is not examined for front matter patterns.
- **FR-008**: Cleaning or extraction rules MUST be selectable by source type
  (`rulebook`, `supplement`, `handwritten`, `novel`), declared at ingestion time.
  Each source type MUST have a documented rule profile. Defined profiles:
  `rulebook` — all rules active (table/stat block reconstruction, de-hyphenation,
  TOC stripping, front matter stripping);
  `supplement` — identical to `rulebook` (all rules active);
  `novel` — de-hyphenation and front matter stripping only (no table or stat block
  reconstruction);
  `handwritten` — de-hyphenation only.
- **FR-009**: The entire pre-processing pipeline MUST be bypassable via an environment
  variable (`KNOWLEDGE_CLEANING_ENABLED`, default `true`), requiring no code changes to
  disable — this allows A/B comparison of chunking quality with and without pre-processing.
- **FR-010**: Every structural transformation applied MUST be logged at `WARNING` level,
  naming the source document and describing what changed (e.g., "Reconstructed 3 stat
  blocks in chapter 4", "Stripped TOC section (22 lines)", "Re-joined 41 hyphenated
  line-breaks"). No transformation may be silent (Principle VIII).
- **FR-011**: Unrecognised content MUST pass through unchanged and be logged at `DEBUG`
  level. No exception may be raised on unrecognised patterns (Principle VII).
- **FR-012**: The cleaning and extraction logic MUST be independently testable using
  plain Markdown input and plain Markdown output — no vector store, LLM, or embedder
  required for unit tests.
- **FR-014**: The existing document upload form in the Gradio UI MUST include a source-type
  dropdown field (`rulebook`, `supplement`, `handwritten`, `novel`). The selected value is
  passed to the ingestion pipeline and stored with the document record so cleaning rules
  are applied correctly. If the user does not change the dropdown, it MUST default to
  `rulebook`.
- **FR-013**: After deployment and re-ingestion, the gold standard evaluation MUST be
  re-run and the resulting MRR, nDCG, and Recall@10 scores recorded in this spec's
  research document. Pre-processing is confirmed beneficial only if at least one metric
  meets or exceeds the spec 007 agentic-chunker baseline.

### Key Entities

- **CleanedDocument**: The text delivered to the chunker after all pre-processing —
  a Markdown string with all applicable transformations applied, plus a `CleaningReport`.
- **CleaningReport**: Structured summary of transformations applied during one ingestion
  run: counts and locations of hyphens re-joined, TOC lines removed, front matter lines
  removed, stat blocks reconstructed, multi-column tables reconstructed. Emitted to the
  application log.
- **SourceType**: Declared document category (`rulebook`, `supplement`, `handwritten`,
  `novel`). Determines which extraction improvements and cleaning rules are active.
  Set at ingestion time via the Gradio UI; defaults to `rulebook`.
- **CleaningRuleProfile**: The set of enabled rules for a given source type. Documented
  and version-controlled so changes to profiles are auditable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After ingestion, zero chunks in the vector store contain exclusively TOC
  entry lines or front matter text from any ingested rulebook.
- **SC-002**: Gold standard questions whose answers reside in stat blocks or multi-column
  tables return coherent, correctly ordered content — not garbled interleaved fragments.
- **SC-003**: The gold standard evaluation with pre-processing enabled produces equal or
  higher mean MRR and Recall@10 compared to the spec 007 agentic-chunker baseline —
  pre-processing MUST NOT regress retrieval quality.
- **SC-004**: At least one gold standard metric (MRR, nDCG, or Recall@10) improves over
  the spec 007 agentic-chunker baseline when pre-processing is enabled.
- **SC-005**: A developer can disable the entire pre-processing pipeline by changing one
  environment variable and re-running ingestion — no code changes required.
- **SC-006**: All transformations applied during an ingestion run are visible in the
  application log at WARNING level — none are silent.
- **SC-007**: Ingesting a PDF that has no structured layout artifacts, no hyphenation
  breaks, no TOC, and no front matter produces functionally equivalent chunker input
  regardless of whether pre-processing is enabled — same content, same Markdown structure,
  no additions or removals — confirming no false-positive transformations.

## Clarifications

### Session 2026-06-25

- The scope of this spec covers the full pre-chunking pipeline: both improvements to the
  extraction step (PDF-to-Markdown conversion) and post-extraction cleaning passes are
  in scope. The research phase will determine which approach is best for each problem.
- Multi-column table support must address the full variety of structured layouts in RPG
  rulebooks: tables of any column count, stat blocks, and creature example blocks.
- SC-007 "byte-for-byte identical" replaced with "functionally equivalent" (same content,
  same Markdown structure, no additions or removals) — the original wording was
  unimplementable as a test criterion.
- Q: Does source type selection require a new UI element in the ingestion form, or should
  it be inferred/defaulted? → A: Add a source-type dropdown to the existing document upload
  form in the Gradio UI, defaulting to `rulebook`. Added as FR-014.
- Q: Should `supplement` have the same rule profile as `rulebook` or a distinct one? → A:
  `supplement` is identical to `rulebook` (all rules active). FR-008 updated with full
  profile matrix for all four source types.
- Q: Should bypass be per-rule or all-or-nothing? → A: All-or-nothing only. Single
  `KNOWLEDGE_CLEANING_ENABLED` env var is sufficient. FR-009 unchanged.
- Long-distance intra-book and inter-book connections are deferred to spec 009
  (breadcrumb injection and contextual retrieval).
- Embedding model comparison (qwen3-embedding:4b vs. nomic-embed-text) is deferred to
  spec 009, where re-ingestion will happen anyway when breadcrumbs are added.
- Answer evaluation is deferred to spec 010.

## Assumptions

- Source type is declared by the user at ingestion time via the existing Gradio UI.
  If unspecified, `rulebook` is the default since it is the most common corpus type
  and applies the broadest cleaning rule set.
- Handwritten corpus documents are assumed to be scanned and OCR-converted to Markdown.
  They do not typically contain multi-column tables, stat blocks, or formal TOC sections;
  the pipeline applies only de-hyphenation for this source type.
- The gold standard evaluation (118 questions, spec 007 agentic-chunker baseline scores)
  is the benchmark used to confirm pre-processing improves or does not regress retrieval.
- Re-ingestion of all documents is required after the pipeline is updated. This is
  acceptable at the current development stage.
- The pre-processing step runs within the existing background ingestion pipeline — it is
  not a separate service. Processing time may increase; since ingestion already runs in
  the background, this is acceptable (ingestion latency is not a gate criterion).
- Mobile support remains out of scope.
- LLM synthesis context and answer quality measurement are out of scope (deferred to
  specs 009 and 010 respectively).
