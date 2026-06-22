# Feature Specification: Game Knowledge Q&A (RAG)

**Feature Branch**: `005-rag-qa-system`

**Created**: 2026-06-22

**Status**: Draft

**Input**: User description: "RAG-based Q&A system for answering questions about game rules, lore, and world. Single-page chat UI with source targeting. PDF → MD pipeline with semantic chunking, query expansion, ranked retrieval, and LLM-enriched chunk metadata (headline, summary, topic, access level). Local vector store for MVP. MD files can also be uploaded directly (GM/player notes, summaries) and go straight to the RAG pipeline."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask a Game Question (Priority: P1)

A player or GM opens the Knowledge Q&A page and types a natural language question about the game — rules, lore, world history, creature stats, or narrative context. The system returns a clear, accurate answer drawn from ingested content, together with citations showing which document and section the answer came from.

**Why this priority**: This is the core user value. Without a working question-answer loop with source references, the feature delivers nothing.

**Independent Test**: With at least one document ingested, type "How does combat initiative work?" and confirm an answer is returned with at least one source citation.

**Acceptance Scenarios**:

1. **Given** a rulebook has been ingested, **When** a user asks "How does a Talent work?", **Then** the system returns a plain-language answer and displays the document name and section it came from.
2. **Given** a lore document has been ingested, **When** a user asks "What did the Blood Wood elves think of Throal?", **Then** the system returns relevant lore and cites the source passage.
3. **Given** no relevant content exists in the knowledge base, **When** a user asks an unanswerable question, **Then** the system clearly states it could not find relevant information rather than inventing an answer.

---

### User Story 2 - Ingest a PDF Rulebook (Priority: P2)

A GM uploads a PDF rulebook or setting document. The system converts it to a readable text format, splits it into semantically coherent segments, enriches each segment with metadata, and makes the document queryable.

**Why this priority**: Without ingested content, there is nothing to query. P2 rather than P1 because a seed corpus can be pre-loaded to test P1 independently.

**Independent Test**: Upload a PDF, wait for processing to complete, then confirm the document appears in the knowledge base list and a question drawn from its content returns that document as a source.

**Acceptance Scenarios**:

1. **Given** a GM uploads a PDF, **When** processing completes, **Then** the document appears in the list of ingested sources with its title and access level.
2. **Given** a PDF has been ingested, **When** a user asks a question covered by that PDF, **Then** the answer cites sections from that document.
3. **Given** a PDF with content relevant to both GMs and players, **When** access levels are assigned during ingestion, **Then** subsequent queries respect those access levels.

---

### User Story 3 - Ingest a Markdown File Directly (Priority: P2)

A GM or player writes session notes, a lore summary, or a faction overview as a Markdown file and uploads it directly. The system skips PDF conversion and runs the file straight through the RAG pipeline (enhancement, chunking, embeddings). This supports lightweight, ongoing knowledge contributions alongside formal rulebooks.

**Why this priority**: Peer with PDF ingestion — Markdown files are the simpler path and unlock GM/player notes as a first-class knowledge source.

**Independent Test**: Upload a hand-written `.md` file containing a short lore entry. Confirm it appears in the knowledge base and a question about its content returns a cited answer.

**Acceptance Scenarios**:

1. **Given** a GM uploads a `.md` file, **When** ingestion completes, **Then** the file appears in the knowledge base list.
2. **Given** a Markdown file describes a custom NPC, **When** a user asks about that NPC, **Then** the answer cites the uploaded Markdown file.
3. **Given** a player uploads session notes tagged player-visible, **When** the GM asks about events in those notes, **Then** the GM's answer includes citations from the session notes.

---

### User Story 4 - Access-Controlled Answers (Priority: P3)

A GM can mark content as GM-only at ingestion time. Player queries only draw from player-visible content; GM queries can draw from all content. This prevents hidden plot information and encounter spoilers from leaking to players.

**Why this priority**: Important for real session use but not required to validate the core RAG loop.

**Independent Test**: Ingest content with a GM-only chunk. Log in as a player and ask a question only that chunk can answer; confirm it is not surfaced. Log in as a GM and ask the same question; confirm the GM-only chunk appears.

**Acceptance Scenarios**:

1. **Given** a chunk tagged GM-only, **When** a player submits a question that requires it, **Then** the answer omits that chunk and either cites only public sources or states no public information is available.
2. **Given** a chunk tagged GM-only, **When** a GM submits the same question, **Then** the answer may use the GM-only chunk and cites it accordingly.

---

### User Story 5 - Source Navigation (Priority: P3)

After receiving an answer, the user can inspect the cited passages that contributed to the response. Each citation shows the document name, a section heading or topic label, and an excerpt of the contributing text, so the user can verify accuracy or read further context.

**Why this priority**: Builds trust and usability but does not block the core Q&A loop.

**Independent Test**: Ask any question that yields a result. Confirm each citation in the response shows document name, section label, and a readable passage excerpt.

**Acceptance Scenarios**:

1. **Given** an answer has been returned, **When** the user examines the citations panel, **Then** each citation shows the document name, section heading or topic label, and the relevant passage text.
2. **Given** multiple chunks contributed to an answer, **When** the user views citations, **Then** all contributing sources are listed and ranked by relevance.

---

### Edge Cases

- What happens when an uploaded PDF is corrupted or cannot be converted?
- What happens when an uploaded Markdown file is malformed or empty?
- What happens when the knowledge base contains no content at all?
- What happens when two ingested documents contradict each other on the same rule?
- How does the system behave with very large PDFs (hundreds of pages)?
- What happens when the question is highly ambiguous and could match many unrelated sections?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to type a natural language question and receive a generated answer drawn from ingested content.
- **FR-002**: Every answer MUST include citations identifying which document(s) and section(s) contributed to the response.
- **FR-003**: The system MUST expand user queries internally to improve retrieval coverage before searching the knowledge base.
- **FR-004**: Retrieved content segments MUST be ranked by relevance before being passed to the answer generator.
- **FR-005**: Users MUST be able to upload PDF files; the system MUST convert them to a structured text format before indexing.
- **FR-006**: Users MUST be able to upload Markdown (`.md`) files directly; these MUST skip the conversion step and go straight into the RAG pipeline (chunking, enrichment, embedding).
- **FR-007**: Both ingestion paths (PDF and Markdown) MUST produce the same enriched chunk structure in the knowledge base.
- **FR-008**: Documents MUST be split into semantically coherent segments using an automated process assisted by a language model.
- **FR-009**: Each content segment MUST be enriched with metadata: a headline, a short summary, a topic label, and an access level (GM-only or player-visible).
- **FR-010**: The system MUST enforce access-level filtering: player queries MUST NOT surface GM-only content.
- **FR-011**: The Q&A interface MUST display a clear, user-visible message when no relevant content is found rather than fabricating an answer.
- **FR-012**: The Q&A interface MUST display a clear, user-visible error message if the knowledge service is unavailable.
- **FR-013**: The UI MUST display cited passages alongside answers so users can verify and read source context.
- **FR-014**: The ingestion pipeline MUST be designed to support additional content types in future (session notes, character sheets) without changing the storage or retrieval layer.

### Key Entities

- **Document**: A source material item uploaded by a user (GM or player). Attributes: title, format (PDF or Markdown), access level, ingestion status.
- **Chunk**: A semantically coherent segment of a Document. Attributes: text, headline, summary, topic, access level, source document reference.
- **Query**: A user's natural language question, internally expanded for retrieval.
- **Answer**: The generated response to a Query, composed from ranked Chunks, with citations back to source Chunks.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users receive an answer with at least one source citation within 30 seconds of submitting a question on typical hardware.
- **SC-002**: A GM can upload a PDF and have it fully indexed and queryable within 10 minutes of upload completion.
- **SC-003**: A user can upload a Markdown file and have it queryable within 2 minutes of upload completion.
- **SC-004**: At least 80% of questions asked against a fully ingested rulebook return a cited answer (not a "no content found" response) in informal testing.
- **SC-005**: GM-only content never appears in a player-role session — zero leakage confirmed across all access-control test scenarios.
- **SC-006**: The knowledge base handles at least 3 simultaneously ingested documents without degraded retrieval quality.
- **SC-007**: The Q&A page remains usable (shows a clear placeholder or error message) even when the underlying knowledge service is unavailable.

## Assumptions

- The UI is a single Gradio tab or page; no separate backend service is introduced (per constitution Principle VI and technology stack constraints).
- The local vector store (ChromaDB) is the MVP storage backend; the pipeline sits behind the `packages/rag/` abstraction so swapping providers requires only an environment variable change (Principle II, IV).
- Local embeddings (nomic-embed-text via Ollama) are used for MVP, also behind the abstraction layer.
- The language model for semantic chunking enrichment and answer generation is served locally via Ollama for MVP.
- Documents ingested are the user's own legally-owned materials; the system stores processed chunks only and does not redistribute original copyrighted text verbatim (per constitution IP compliance requirement).
- Access control uses the existing `User`, `Player`, and `GameStar` SQLAlchemy models for role determination (GM vs. player); no new authentication infrastructure is introduced.
- PDF-to-Markdown conversion handles standard text-based PDFs; scanned/image-only PDFs are out of scope for MVP.
- Document deletion and re-ingestion are out of scope for MVP; the knowledge base is append-only in this iteration.
- Session notes and character sheet ingestion share the same pipeline architecture but are deferred to a future spec; the pipeline is designed to accommodate them.
- Mobile support is out of scope; the UI targets desktop browser sessions.