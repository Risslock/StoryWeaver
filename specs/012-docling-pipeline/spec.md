# Feature Specification: Docling Ingestion Pipeline

**Feature Branch**: `012-docling-pipeline`

**Created**: 2026-06-26

**Status**: Draft

**Input**: User description: "Use Docling for the extraction and chunking layers. Keep old cleaning code but clearly mark as deprecated (portfolio/research proof of evolution). Retire CorpusCleaner FR-003 (image placeholders) and FR-004 (furniture separation) — Docling handles these at the extraction layer. Keep stat-block rules. Store meta.headings as breadcrumbs field in chunk metadata to replace BreadcrumbExtractor. Use C effective text (headings prepended) as the ingested chunk content."

---

## Research Baseline

This feature is directly informed by the 012 Docling spike (merged PR #19). Key findings:

| Dimension | pymupdf4llm baseline | Docling result |
|---|---|---|
| Image placeholders in chunks | 96 | 0 |
| Furniture lines in chunk body | Present (headers/footers mixed in) | 0 (moved to metadata) |
| Real structured tables | 1 (1186 pipe-rows) | 86 structured tables |
| Stat-block hits | 79 | 99 |
| Chunks with breadcrumb coverage | Requires BreadcrumbExtractor post-pass | 1392 / 1439 (HybridChunker meta.headings) |
| Stub chunks (effective comparison) | 6 (Run A-proxy) | 0 (Run B) / effectively 0 (Run C) |
| Extraction + chunking time | Baseline | ~30× faster |

**Spike decision**: Adopt Docling end-to-end for extraction and chunking. Retire FR-003 and FR-004 from active CorpusCleaner usage. Replace BreadcrumbExtractor with HybridChunker heading metadata.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Re-ingestion via Docling Pipeline (Priority: P1)

A developer re-ingests the Earthdawn rulebook using the new Docling-backed pipeline. The operation completes dramatically faster than before (approximately 30× improvement). The resulting corpus has zero image placeholder lines, zero furniture noise in chunk bodies, coherent structured tables instead of raw pipe-row fragments, and at least 96% of chunks carry non-empty breadcrumb metadata from the HybridChunker's heading context. The benchmark shows maintained or improved retrieval quality compared to the 011 baseline.

**Why this priority**: The extraction and chunking layers are the foundation of every downstream step — cleaning, embedding, retrieval, and answer quality all depend on them. Replacing them with Docling is the highest-leverage single change in the pipeline. All other stories in this feature depend on this path being in place first.

**Independent Test**: Re-ingest ED4_Players_Guide with the Docling pipeline (default configuration). Inspect the resulting ChromaDB collection. Verify: (a) zero chunks contain lines matching `==> picture` or `--- Start of picture text ---`; (b) zero chunks contain isolated page-number lines (a single integer between blank lines); (c) at least 86 chunks contain structured table content (not raw `|…|…|` pipe rows); (d) at least 96% of chunks have a non-empty `breadcrumb` metadata field; (e) total ingestion time is at most 1/10 of the pymupdf4llm baseline time for the same document.

**Acceptance Scenarios**:

1. **Given** ED4_Players_Guide is ingested with the Docling pipeline, **When** the resulting chunks are inspected, **Then** zero chunks contain image placeholder markup (`==> picture`, `--- Start of picture text ---`, `--- End of picture text ---`).

2. **Given** ED4_Players_Guide is ingested with the Docling pipeline, **When** the resulting chunks are inspected, **Then** zero chunks contain isolated page-header or page-footer lines — all furniture text is captured in document metadata, not chunk bodies.

3. **Given** a PDF page contains a structured table (stat block, gear table, spell table), **When** Docling processes that page, **Then** the chunk containing the table represents it as coherent structured Markdown — not as 10–30 individual pipe-row fragments split across separate chunks.

4. **Given** a PDF page contains stat blocks (Earthdawn creature stats, ability scores, attack entries), **When** CorpusCleaner stat-block rules run on the Docling output, **Then** the stat-block detection rate meets or exceeds the spike result of 99 hits (vs 79 for pymupdf4llm baseline).

5. **Given** ED4_Players_Guide is re-ingested using the Docling pipeline, **When** ingestion completes, **Then** the total wall-clock time is at most 1/10 of the wall-clock time recorded for an equivalent pymupdf4llm ingestion run on the same hardware.

---

### User Story 2 — Breadcrumb-Enriched Chunks via HybridChunker Headings (Priority: P2)

A developer queries the corpus with a navigation-dependent question ("What are the rules for Thread Weaving in the Elementalist discipline?"). Because every chunk carries a `breadcrumb` field derived from the HybridChunker's `meta.headings`, the retriever can surface contextually relevant chunks even when the question keyword does not appear in the chunk body. The "C effective" format (heading path prepended to `original_text`) means the embedding encodes positional context — not just the raw prose.

**Why this priority**: Heading context is the dominant differentiator between the old pipeline (BreadcrumbExtractor post-pass, 0-coverage baseline) and Run C from the spike (96.7% coverage with zero extra infrastructure). This replaces a separate extraction step with data already produced by the chunker.

**Independent Test**: After Docling ingestion, query ChromaDB for 10 heading-dependent questions whose answers require knowing *where in the book* the chunk lives (e.g., discipline-specific rules). Verify: (a) at least 8 of 10 retrieved top-1 chunks have a non-empty `breadcrumb` metadata field; (b) the `breadcrumb` value accurately represents the heading path from the document section the chunk comes from; (c) `KnowledgeChunk.text` returned to the query handler begins with the heading path prefix followed by the body text.

**Acceptance Scenarios**:

1. **Given** the HybridChunker produces a chunk with `meta.headings = ["Chapter 5", "Elementalist", "Thread Weaving"]`, **When** the chunk is stored in ChromaDB, **Then** its metadata contains `breadcrumb: "Chapter 5 > Elementalist > Thread Weaving"` — assembled from `meta.headings` using the `" > "` separator.

2. **Given** the HybridChunker produces a chunk with `meta.headings`, **When** the chunk is stored in ChromaDB, **Then** the `original_text` field is the "C effective" format: `[breadcrumb]\n\n[body text]`. The retriever returns this value as `KnowledgeChunk.text` to query handlers.

3. **Given** a chunk whose HybridChunker result carries `meta.headings = []` (root-level content with no section heading), **When** the chunk is stored, **Then** `breadcrumb` is an empty string (not absent, not null) and `original_text` is the body text without a heading prefix.

4. **Given** 1439 chunks produced by the HybridChunker for ED4_Players_Guide, **When** all chunks are inspected, **Then** at least 1392 carry a non-empty `breadcrumb` metadata field — matching the spike's 96.7% coverage.

---

### User Story 3 — Deprecated Pipeline Code as Portfolio Research Artifact (Priority: P3)

A reviewer of the StoryWeaver portfolio can navigate the codebase and clearly identify which code belongs to the original pymupdf4llm extraction and chunking pipeline vs. the new Docling pipeline. The old code is present, undeleted, and prominently marked `@deprecated` with a comment referencing the spike finding and the feature number that supersedes it. The portfolio narrative — research spike → documented findings → incremental adoption with proof of old approach — is legible directly from the source.

**Why this priority**: Portfolio continuity is an explicit non-functional goal. Deleting the old pipeline removes the evidence of the research process. Clear deprecation markers ensure the old code is understandable in context rather than orphaned.

**Independent Test**: Open the old extractor module and the old chunker. Verify: (a) each contains a module-level deprecation notice referencing the Docling spike (feature 012) and the spike PR number; (b) each has a class-level or function-level `@deprecated` marker or docstring annotation; (c) the old code path can still be invoked by passing a `use_legacy=True` flag or equivalent — it produces output without crashing, but emits a deprecation warning to the log at `WARNING` level.

**Acceptance Scenarios**:

1. **Given** the legacy pymupdf4llm extractor module, **When** a developer opens it, **Then** the module docstring or a top-of-file comment states it is deprecated since feature 012, names the Docling replacement, and links to the spike PR or spike notebook.

2. **Given** the legacy chunker module, **When** a developer opens it, **Then** the same deprecation notice is present with equivalent content.

3. **Given** CorpusCleaner is invoked on Docling output, **When** the image-placeholder rule (FR-003 from feature 011) or the furniture/page-number rule (FR-004 from feature 011) would match, **Then** those rules are marked `@deprecated` in source (with a comment that Docling handles this at the extraction layer) and MUST NOT be applied to Docling-extracted content — they remain in code as documented dead paths, not active filters.

4. **Given** any code path that uses the legacy extractor or legacy chunker is invoked, **When** it runs, **Then** the logger emits a `WARNING`-level deprecation message naming the class/function and the replacement.

---

### User Story 4 — Provider-Selectable Ingestion Models (Priority: P2)

A developer can switch the ingestion pipeline's enrichment LLM and embedding model between local Ollama and HuggingFace free tier by changing two env vars in `.env` and restarting — no code changes required. Every model name is an explicit env var entry; there are no hidden code-level fallbacks. If a required env var is missing or a provider key is blank, the pipeline aborts immediately with a clear error naming the specific missing variable. The same ingestion pipeline that runs fully offline on a laptop also runs against the HuggingFace free tier in a cloud or CI environment with no code modification.

**Why this priority**: Provider lock-in is an explicit architecture risk (Constitution Principle II). The knowledge pipeline currently hardcodes Ollama at three instantiation sites, making provider switching require code edits. This story unblocks the pipeline from a local-only constraint and follows the same factory pattern already established by the image generation provider. It is P2 (not P1) because the pipeline functions correctly without it — it is an enablement story, not a correctness story.

**Independent Test**: Set `KNOWLEDGE_ENRICH_PROVIDER=huggingface`, `KNOWLEDGE_EMBED_PROVIDER=huggingface`, `HF_API_KEY=<valid key>`, `KNOWLEDGE_ENRICH_MODEL=<valid HF text-generation model>`, `KNOWLEDGE_EMBED_MODEL=<valid HF feature-extraction model>`, and unset `OLLAMA_BASE_URL`. Run a minimal ingestion (5-page document). Verify: (a) enrichment LLM calls go to HuggingFace, not Ollama; (b) embedding calls go to HuggingFace, not Ollama; (c) ChromaDB contains chunks with populated `headline`, `summary`, `topic`, `access_level`, and `breadcrumb` fields. Then switch back to Ollama by changing the two provider vars. Verify the same ingestion run succeeds locally.

**Acceptance Scenarios**:

1. **Given** `KNOWLEDGE_ENRICH_PROVIDER=huggingface` and a valid `HF_API_KEY`, **When** the ingestion pipeline runs, **Then** enrichment LLM calls are sent to the HuggingFace Inference API — no calls are made to the Ollama endpoint for enrichment.

2. **Given** `KNOWLEDGE_EMBED_PROVIDER=huggingface` and a valid `HF_API_KEY`, **When** the embedding step runs, **Then** embedding vectors are produced via the HuggingFace Inference API feature-extraction endpoint — no calls are made to the Ollama embedding endpoint.

3. **Given** `KNOWLEDGE_ENRICH_PROVIDER=ollama` and `KNOWLEDGE_EMBED_PROVIDER=ollama`, **When** the ingestion pipeline runs, **Then** all LLM and embedding calls go exclusively to the local Ollama instance — no external API calls are made.

4. **Given** `KNOWLEDGE_ENRICH_MODEL` is not set in the environment, **When** the pipeline starts, **Then** it logs an ERROR: `"KNOWLEDGE_ENRICH_MODEL is required but not set"` and aborts before processing any document — it MUST NOT fall back to a code-level default model name.

5. **Given** `KNOWLEDGE_EMBED_MODEL` is not set in the environment, **When** the embedding step initialises, **Then** it logs an ERROR: `"KNOWLEDGE_EMBED_MODEL is required but not set"` and aborts — it MUST NOT fall back to a code-level default.

6. **Given** `KNOWLEDGE_ENRICH_PROVIDER=huggingface` but `HF_API_KEY` is absent or blank, **When** the pipeline starts, **Then** it logs an ERROR: `"HF_API_KEY is required when KNOWLEDGE_ENRICH_PROVIDER=huggingface"` and aborts — it MUST NOT attempt any API calls with an empty token.

7. **Given** `KNOWLEDGE_ENRICH_PROVIDER` is not set in the environment, **When** the pipeline starts, **Then** it logs an ERROR: `"KNOWLEDGE_ENRICH_PROVIDER is required but not set (accepted values: ollama, huggingface)"` and aborts.

---

### Edge Cases

- What if Docling's furniture detection incorrectly classifies a frontmatter or copyright page as body content? The affected chunks will carry the copyright text as body text; a follow-up audit against the spike edge-case checklist should confirm no leakage into the main corpus.
- What if a chunk has `meta.headings` with entries that include Markdown formatting characters (bold, italic, hash prefixes)? The `breadcrumb` assembly MUST strip formatting characters before joining, preserving the plain-text heading name only.
- What if the HybridChunker produces a chunk that is a stub (very short text, heading-only)? The post-chunk quality gate from feature 011 (minimum chunk size) should still apply to Docling output.
- What if Docling fails to parse a specific PDF (unsupported format, encrypted, corrupt)? The pipeline MUST log an `ERROR` with the file path and Docling's reported reason and abort ingestion for that file — it MUST NOT silently produce an empty corpus.
- What if a document has zero sections with headings (flat prose PDF)? All chunks will have `meta.headings = []`; all `breadcrumb` values will be empty strings; `original_text` will be body-only (no heading prefix) for all chunks. This is valid output and must not cause errors downstream — the retriever will return `KnowledgeChunk.text` without a heading prefix.
- What if the deprecated legacy extractor is accidentally invoked on a production ingestion path? The `WARNING`-level deprecation log ensures the operator is informed; the code path continues to function to avoid silent failures.
- What if `KNOWLEDGE_ENRICH_PROVIDER=huggingface` but `HF_API_KEY` is set to a blank string (present but empty)? A blank string MUST be treated the same as absent — the pipeline MUST abort with an ERROR before making any API calls. An empty token would result in silent 401 errors deep in the ingestion run.
- What if a HuggingFace model name is specified that does not support the required inference task (e.g., an image generation model name used as the enrichment LLM)? The pipeline will receive an error or malformed response from the HF Inference API; this MUST be surfaced as an ERROR-level log with the model name and the API error message — it MUST NOT be swallowed or retried silently.
- What if `KNOWLEDGE_EMBED_PROVIDER=huggingface` and the specified model does not support the feature-extraction task? The HF Inference API will return an error on the first embedding batch call; the pipeline MUST surface this as an ERROR and abort ingestion for that document.
- What if `KNOWLEDGE_ENRICH_PROVIDER` and `KNOWLEDGE_EMBED_PROVIDER` use different backends (e.g., `ollama` for enrichment and `huggingface` for embeddings)? This is a valid combination and MUST work — the two factories are independent. The pipeline MUST NOT assume both providers are the same.

---

## Requirements *(mandatory)*

### Functional Requirements

**Extraction Layer — Docling Adoption**

- **FR-001**: The ingestion pipeline MUST use Docling's document conversion API as the primary PDF-to-structured-document layer, replacing pymupdf4llm. Docling's output document object MUST be the input to the chunking layer.
- **FR-002**: Docling's output MUST be accepted as-is for furniture handling (headers, footers, page numbers): these elements MUST NOT appear in chunk body text. The existing CorpusCleaner rules for image placeholder stripping (FR-003 from feature 011) and furniture/page-number stripping (FR-004 from feature 011) MUST be marked deprecated and MUST NOT be applied to Docling-extracted content.
- **FR-003**: CorpusCleaner stat-block detection rules (game-specific entity recognition for Earthdawn stat blocks) MUST be retained and applied to Docling output. These rules are NOT deprecated — Docling demonstrates improved stat-block surface area (99 hits vs 79 baseline) and the rules remain valid.
- **FR-004**: Docling's frontmatter and copyright page handling via furniture metadata MUST be verified against edge cases in the ED4_Players_Guide. Any pages incorrectly classified as body content (vs. furniture) MUST be documented as known limitations if they cannot be resolved within this feature's scope.

**Chunking Layer — HybridChunker Adoption**

- **FR-005**: The chunking layer MUST use Docling's HybridChunker to produce chunks from the Docling document object, replacing the current chunker.
- **FR-006**: Each chunk produced by HybridChunker MUST expose `meta.headings` (the list of heading strings from the document structure above the chunk). The pipeline MUST use this field as the source of breadcrumb data.

**Breadcrumb Metadata — Replacing BreadcrumbExtractor**

- **FR-007**: For each chunk, the pipeline MUST assemble a `breadcrumb` string by joining the entries in `meta.headings` with the separator `" > "`. This value MUST be stored in the chunk's ChromaDB metadata under the key `breadcrumb` — matching the field name used by `KnowledgeChunk` and `ChromaVectorStore`.
- **FR-008**: Before assembling the `breadcrumb` string, each heading entry from `meta.headings` MUST have all Markdown formatting characters stripped (`*`, `_`, `#`, `` ` ``). The plain-text heading name is used; Markdown syntax is not.
- **FR-009**: When `meta.headings` is empty or absent, `breadcrumb` MUST be stored as an empty string (`""`). The field MUST always be present in chunk metadata.
- **FR-010**: BreadcrumbExtractor MUST be marked deprecated in source with a comment stating that Docling HybridChunker's `meta.headings` supersedes it (since feature 012). BreadcrumbExtractor MUST NOT be invoked in the active ingestion pipeline.

**Chunk Content — "C Effective" Format**

- **FR-011**: The `original_text` field stored in ChromaDB metadata for each chunk MUST use the "C effective" format: if `breadcrumb` is non-empty, `original_text` is `[breadcrumb]\n\n[body text]`. If `breadcrumb` is empty, `original_text` is the body text alone. `original_text` is the value returned as `text` in `KnowledgeChunk` during retrieval — this is what downstream query handlers and the UI receive.
- **FR-012**: The `breadcrumb` prefix in the "C effective" `original_text` MUST use the same assembled string as the `breadcrumb` metadata field — they MUST be identical. The existing pipeline's compound-text construction (which prepends `breadcrumb` alongside enrichment fields for embedding) remains unchanged; "C effective" enriches the `raw_text` component of that compound text.

**Legacy Code Preservation — Deprecation Markers**

- **FR-013**: The legacy pymupdf4llm extractor module MUST carry a module-level deprecation notice stating: deprecated since feature 012, superseded by Docling, referencing the spike PR number. The module MUST NOT be deleted.
- **FR-014**: The legacy chunker module MUST carry an equivalent module-level deprecation notice.
- **FR-015**: Any code path that instantiates or calls legacy extractor or legacy chunker classes/functions MUST emit a `WARNING`-level log message: `"[ClassName/function_name] is deprecated since feature 012 — use the Docling pipeline instead."` This includes test utilities and notebooks that invoke the legacy path.
- **FR-016**: The deprecated CorpusCleaner rules (image placeholder stripper, furniture/page-number stripper) MUST be marked with inline `# DEPRECATED(012)` comments and MUST NOT be included in the active cleaning step applied to Docling output.

**Downstream Pipeline Compatibility**

- **FR-017**: Every chunk produced by the Docling pipeline MUST carry `extraction_mode: "docling"` in its ChromaDB metadata — distinguishing it from historical pymupdf4llm runs (which used `"text"`) and enabling benchmark filtering by pipeline version.
- **FR-018**: The `source_type` field in ChromaDB metadata MUST be passed through from the ingestion document configuration unchanged. The Docling pipeline MUST NOT alter the `source_type` value — it continues to be set by the caller (`"rulebook"`, `"supplement"`, `"handwritten_note"`, or `"novel"`).
- **FR-019**: `ChunkEnricher` and `ChromaVectorStore` MUST operate on Docling pipeline output without modification. The Docling pipeline is responsible for producing the chunk text (FR-011) and `breadcrumb` metadata (FR-007). `ChunkEnricher.enrich_chunks()` receives the HybridChunker body text and produces `headline`, `summary`, `topic`, and `access_level` fields as before; the compound-text assembly for embedding remains unchanged (breadcrumb + contextual summary + headline + summary + original_text). The embedding function is now provider-selected (FR-024) rather than hardcoded to `OllamaEmbedFn`.

**Provider Selection & Model Configuration**

- **FR-020**: The ingestion pipeline MUST read `KNOWLEDGE_ENRICH_PROVIDER` from the environment to select the enrichment LLM provider. Accepted values: `"ollama"` | `"huggingface"`. If this variable is absent or set to an unrecognised value, the pipeline MUST log an ERROR — `"KNOWLEDGE_ENRICH_PROVIDER is required (accepted: ollama, huggingface)"` — and abort before processing any document.
- **FR-021**: The embedding step MUST read `KNOWLEDGE_EMBED_PROVIDER` from the environment to select the embedding provider. Accepted values: `"ollama"` | `"huggingface"`. If absent or unrecognised, the pipeline MUST log an ERROR — `"KNOWLEDGE_EMBED_PROVIDER is required (accepted: ollama, huggingface)"` — and abort.
- **FR-022**: `KNOWLEDGE_ENRICH_MODEL` and `KNOWLEDGE_EMBED_MODEL` MUST be read from the environment with no code-level fallback string. If either is absent or blank at startup, the pipeline MUST log an ERROR naming the specific missing variable and abort. This requirement applies regardless of which provider is selected — there is no default model name embedded in code.
- **FR-023**: When `KNOWLEDGE_ENRICH_PROVIDER=ollama`, the enrichment step MUST use `OllamaProvider` with `OLLAMA_BASE_URL` and `KNOWLEDGE_ENRICH_MODEL`. When `KNOWLEDGE_ENRICH_PROVIDER=huggingface`, it MUST use the existing `HuggingFaceLLMProvider` (already implemented in `packages/llm/`) with `HF_API_KEY` and `KNOWLEDGE_ENRICH_MODEL`. No other code changes are required to `ChunkEnricher` — it already accepts any `LLMProvider` in its constructor.
- **FR-024**: When `KNOWLEDGE_EMBED_PROVIDER=ollama`, the embedding step MUST use `OllamaEmbedFn` with `OLLAMA_BASE_URL` and `KNOWLEDGE_EMBED_MODEL`. When `KNOWLEDGE_EMBED_PROVIDER=huggingface`, it MUST use a new `HuggingFaceEmbedFn` implementation (to be created in `packages/rag/`) that calls the HuggingFace Inference API feature-extraction endpoint with `HF_API_KEY` and `KNOWLEDGE_EMBED_MODEL`.
- **FR-025**: Provider selection for enrichment and embedding MUST be implemented as factory functions — one for the enrichment LLM (`get_knowledge_enrich_provider()`) and one for the embedding function (`get_knowledge_embed_fn()`). These factories read the provider env vars (FR-020, FR-021) and instantiate the correct implementation. All direct `OllamaProvider()` and `OllamaEmbedFn()` instantiations in the knowledge ingestion pipeline (`pipeline.py`, `retriever.py`, and any other knowledge-package call site) MUST be replaced with calls to these factories. This follows the existing `get_image_provider()` pattern in `packages/imagegen/imagegen/factory.py`.
- **FR-026**: `HF_API_KEY` is required when any knowledge pipeline provider is set to `"huggingface"`. If `HF_API_KEY` is absent or blank at startup and a HuggingFace provider is selected, the pipeline MUST log an ERROR — `"HF_API_KEY is required when KNOWLEDGE_ENRICH_PROVIDER=huggingface"` (or equivalent for embed) — and abort before making any external API calls.
- **FR-027**: `.env.example` MUST document all new provider and model env vars (`KNOWLEDGE_ENRICH_PROVIDER`, `KNOWLEDGE_EMBED_PROVIDER`, `KNOWLEDGE_ENRICH_MODEL`, `KNOWLEDGE_EMBED_MODEL`) with commented examples showing both the Ollama and HuggingFace configurations side by side, so a developer can switch between them by editing a single block.

### Key Entities

- **DoclingDocument**: The structured document object produced by Docling's conversion API. This is the intermediate representation between PDF bytes and chunks — it carries layout, tables, headings, and furniture metadata. Replaces the raw Markdown string previously produced by pymupdf4llm.
- **HybridChunk**: A chunk produced by Docling's HybridChunker, carrying `text` (body), `meta.headings` (heading path list), and associated metadata. This is the new canonical chunk representation before storage.
- **OriginalText** (ChromaDB field `original_text`): The "C effective" text stored per chunk — the `breadcrumb` heading path prepended to the body text with a blank-line separator, or body-only when `breadcrumb` is empty. This is what the retriever returns as `KnowledgeChunk.text` to query handlers and the UI.
- **BreadcrumbField** (ChromaDB metadata key `breadcrumb`): The `" > "`-joined, Markdown-stripped string assembled from `meta.headings`. Stored under the existing `breadcrumb` key in `ChromaVectorStore` metadata and prepended to body text in `original_text`. Matches the `breadcrumb` field of `KnowledgeChunk`.
- **ChunkEnrichment** (existing, unchanged): The `headline`, `summary`, `topic`, and `access_level` fields produced by `ChunkEnricher` for each chunk. These fields are populated downstream — the Docling pipeline produces the text that `ChunkEnricher` receives; it does not produce enrichment fields itself.
- **KnowledgeEnrichProvider** (env var `KNOWLEDGE_ENRICH_PROVIDER`): The provider selector for the enrichment LLM. Must be `"ollama"` or `"huggingface"`. Required — no default. Controls which `LLMProvider` implementation `ChunkEnricher` receives.
- **KnowledgeEmbedProvider** (env var `KNOWLEDGE_EMBED_PROVIDER`): The provider selector for the embedding function. Must be `"ollama"` or `"huggingface"`. Required — no default. Controls which embedding function the pipeline uses.
- **HuggingFaceEmbedFn** (new): An embedding implementation to be created in `packages/rag/` that calls the HuggingFace Inference API feature-extraction endpoint. Parallel to the existing `OllamaEmbedFn`; selected when `KNOWLEDGE_EMBED_PROVIDER=huggingface`.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After Docling re-ingestion of ED4_Players_Guide, zero chunks in the resulting collection contain image placeholder markup (`==> picture`, `--- Start of picture text ---`).
- **SC-002**: After Docling re-ingestion, zero chunks contain isolated furniture lines (page headers, page footers, or standalone page-number integers between blank lines) in their body text.
- **SC-003**: After Docling re-ingestion, the corpus contains at least 86 chunks with coherent structured table content — the 86 real tables identified in the spike, rather than 1186 pipe-row fragments distributed across hundreds of micro-chunks.
- **SC-004**: After Docling re-ingestion, at least 96.7% of chunks (matching the spike result of 1392/1439) carry a non-empty `breadcrumb` metadata field.
- **SC-005**: Docling end-to-end ingestion time (extraction + chunking) for ED4_Players_Guide is at most 1/10 of the wall-clock time for an equivalent pymupdf4llm ingestion run recorded before this feature, on the same hardware.
- **SC-006**: After Docling re-ingestion, stat-block detection in CorpusCleaner identifies at least 99 stat-block hits in ED4_Players_Guide (matching the spike result — an improvement from the 79 hits in the pymupdf4llm baseline).
- **SC-007**: The gold standard Recall@10 after Docling re-ingestion is at least equal to the feature 011 text-path baseline recorded in `benchmark_results.jsonl` (no regression). Improvement is expected but not enforced as a hard gate.
- **SC-008**: Every chunk stored in ChromaDB carries: (a) a `breadcrumb` key in metadata (empty string or non-empty — never absent); (b) an `original_text` field whose value is the "C effective" text (heading path prepended when `breadcrumb` is non-empty); (c) an `extraction_mode` field set to `"docling"`; (d) a `source_type` field matching the ingestion document configuration.
- **SC-009**: The legacy extractor and legacy chunker modules are present in the codebase with deprecation notices, and at least one integration test confirms that invoking the legacy path emits a `WARNING`-level log message without crashing.
- **SC-010**: A full re-ingestion of ED4_Players_Guide using the Docling pipeline succeeds end-to-end — chunks pass through `ChunkEnricher`, the selected embedding function, and `ChromaVectorStore` without schema errors or missing required metadata fields. The retriever returns `KnowledgeChunk` objects with all fields populated (`headline`, `summary`, `topic`, `access_level`, `breadcrumb`, `source_type`, `extraction_mode`) for every retrieved chunk.
- **SC-011**: Starting the ingestion pipeline with any required model or provider env var absent produces an ERROR-level log message naming every missing variable within 1 second of startup — no partial document processing occurs, no silent default is applied.
- **SC-012**: Switching `KNOWLEDGE_ENRICH_PROVIDER` and `KNOWLEDGE_EMBED_PROVIDER` from `"ollama"` to `"huggingface"` (with a valid `HF_API_KEY` and valid HuggingFace model names in `KNOWLEDGE_ENRICH_MODEL` and `KNOWLEDGE_EMBED_MODEL`) completes a full ingestion run of ED4_Players_Guide without any code changes — only env var edits.

---

## Assumptions

- Docling is added as a project dependency (`docling` package via `uv`). This is a new top-level dependency not previously in the project. An Architecture Decision Record is not required (the spike already ratified this choice), but the dependency MUST be documented in `pyproject.toml`.
- The Docling HybridChunker's `meta.headings` field is a list of strings. This was validated in the spike against ED4_Players_Guide. Other PDF structures may produce empty lists at the document root level — this is handled by FR-009.
- "C effective" format means: heading path string prepended to body text, stored as `original_text` in ChromaDB. The spike's Run C showed this format produces better chunk coherence than body-only text (Run B). The heading prefix is the same `" > "`-joined string as the `breadcrumb` metadata field.
- The vision LLM extraction path specified in feature 011 (FR-010 through FR-015) is superseded by Docling's own layout analysis and table extraction. Docling's extraction quality for complex RPG PDFs (tables, stat blocks, multi-column) covers the primary motivation for the vision path. The vision path work from 011 is therefore not carried forward into 012 — it is considered deferred/superseded.
- The post-chunk quality gate from feature 011 (minimum chunk size 150 chars, maximum chunk size 15,000 chars) remains applicable and MUST still be applied to HybridChunker output.
- The frontmatter and copyright page edge case is flagged as a known open item. If Docling misclassifies these pages, the finding will be documented as a known limitation. Resolution (if needed) is deferred to a follow-up feature.
- Full re-ingestion is required to apply the new pipeline. There is no partial migration path — the entire ChromaDB collection for affected documents must be rebuilt.
- The deprecated legacy code paths are retained indefinitely for portfolio purposes. They are not scheduled for removal.
- BreadcrumbExtractor from feature 010 is replaced — not extended or adapted. Its source remains in the codebase, marked deprecated, for the same portfolio continuity reason.
- `HuggingFaceLLMProvider` already exists in `packages/llm/llm/providers/huggingface.py` and is the implementation to wire for enrichment. No new LLM provider class is required for FR-023.
- `HuggingFaceEmbedFn` does NOT yet exist and MUST be created as part of this feature (FR-024). It calls the HuggingFace Inference API feature-extraction endpoint. The existing `OllamaEmbedFn` is the structural reference.
- The HuggingFace free tier has rate limits (requests per minute and per month). For a 1439-chunk document, embedding calls will be batched. If the HF API returns a rate-limit error, the pipeline MUST surface it as an ERROR-level log and abort — no automatic retry or backoff logic is in scope for this feature.
- `KNOWLEDGE_ENRICH_PROVIDER` and `KNOWLEDGE_EMBED_PROVIDER` are independent — using `"ollama"` for one and `"huggingface"` for the other is valid and explicitly supported.
- `OLLAMA_BASE_URL` is an existing env var (`http://localhost:11434` is the conventional default in `.env.example`). Unlike model name vars, it is acceptable for the Ollama URL to have a conventional default since it does not affect output quality — only connectivity. Model name vars MUST NOT have code-level defaults.
- The `KNOWLEDGE_ENRICH_PROVIDER` and `KNOWLEDGE_EMBED_PROVIDER` vars are new; they do not replace the existing `LLM_PROVIDER` and `EMBEDDING_PROVIDER` settings (which were defined in `core/config.py` but remain unused for provider dispatch). The new knowledge-scoped vars give the knowledge pipeline its own independent selector, avoiding conflicts with other packages that may later adopt the global vars.

---

## Clarifications

### Session 2026-06-26

- Q: Should the vision extraction path from feature 011 be preserved alongside Docling? → A: No — Docling's layout analysis and table extraction covers the core motivation for vision extraction (complex layouts, tables, multi-column). The vision path is superseded by this feature. The 011 spec documents why it was proposed; no code for it was merged.
- Q: Should the "C effective" heading prefix use the raw `meta.headings` list entries or the Markdown-stripped versions? → A: Markdown-stripped (same as the `breadcrumb` metadata field) — consistency between the `original_text` prefix and the stored `breadcrumb` metadata key is required (FR-012).
- Q: Are the minimum/maximum chunk size gates from 011 (FR-007, FR-008) still applicable to HybridChunker output? → A: Yes — they remain as pipeline steps applied after chunking, regardless of chunker.
- Q: Should the provider selector use the existing global `LLM_PROVIDER`/`EMBEDDING_PROVIDER` or knowledge-scoped vars? → A: Knowledge-scoped vars (`KNOWLEDGE_ENRICH_PROVIDER`, `KNOWLEDGE_EMBED_PROVIDER`) so the knowledge pipeline is independently configurable without affecting other packages. The global vars exist in settings but remain unused for now.
- Q: Should model name env vars have code-level defaults? → A: No. All model name vars (`KNOWLEDGE_ENRICH_MODEL`, `KNOWLEDGE_EMBED_MODEL`) MUST be required — absent means abort with ERROR. The model choice is "important logic" that must always be visible in the env file (FR-022).
