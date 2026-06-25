# Feature Specification: RAG Evaluation Tab & Q&A Source Visibility

**Feature Branch**: `006-rag-eval-qa-ux`

**Created**: 2026-06-22

**Status**: Draft

**Input**: User description: "The rag system is working but the answers are pretty bad. Lets create an
evaluation tap (just for GMs) to see how the system is retrieving and answering. Base the idea on the
eval.py and test.py i'm attaching as context. The main metrics i want to evaluate are: mrr, ndcg and
recall at k. I'll prepare a jsonl file with predefined questions, key works, answers and category of the
questions. Finally, on the Q&A tap separate the response from the llm from the cited sources, it is
better to have it on the side or hidden and just show it when requested from the user."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - GM Runs RAG Retrieval Evaluation (Priority: P1)

A GM opens the Evaluation tab and selects a pre-built JSONL test file containing questions, expected
keywords, reference answers, and category labels. The system processes each test question through the
RAG retrieval pipeline and reports MRR, nDCG, and Recall@k scores per question, plus aggregate means
across the full test set.

**Why this priority**: Without retrieval metrics the team has no objective signal for whether indexing
or retrieval changes are helping or hurting. This is the core diagnostic capability.

**Independent Test**: Load the JSONL file, run evaluation on all questions, verify that MRR/nDCG/Recall@k
values are numeric and bounded [0, 1], and that per-question rows match the number of JSONL entries.

**Acceptance Scenarios**:

1. **Given** a GM is logged in and opens the Evaluation tab, **When** they load a valid JSONL test file,
   **Then** the tab displays a table of test questions with their category.
2. **Given** a loaded test file, **When** the GM triggers evaluation, **Then** each row shows MRR, nDCG,
   and Recall@k scores alongside the question and category.
3. **Given** evaluation is complete, **Then** aggregate mean MRR, mean nDCG, and mean Recall@k are
   displayed as a summary above or below the per-question table.
4. **Given** a non-GM user is logged in, **When** they try to access the Evaluation tab,
   **Then** the tab is not visible or is access-denied.

---

### User Story 2 - GM Inspects a Single Question's Retrieval Detail (Priority: P2)

After seeing a low score for a particular question, the GM selects that row to inspect which documents
were retrieved, whether the expected keywords were found, and at which rank each keyword first appeared.

**Why this priority**: Aggregate scores tell you something is wrong; per-question drill-down tells you
why. Without it, fixing retrieval is guesswork.

**Independent Test**: Select a single test question, trigger retrieval, and verify that retrieved
document excerpts and per-keyword rank information are shown.

**Acceptance Scenarios**:

1. **Given** evaluation results are shown, **When** the GM selects a question row,
   **Then** the system shows the retrieved document snippets (top-k) and a per-keyword breakdown
   (keyword, found at rank N or "not found").
2. **Given** a keyword is not present in any retrieved document, **Then** its rank shows "not found"
   and contributes 0 to MRR and nDCG.

---

### User Story 3 - Q&A Tab Shows LLM Answer Separately From Cited Sources (Priority: P3)

Any user submitting a question on the Q&A tab sees the LLM-generated answer immediately. Cited sources
(the retrieved document chunks used to generate the answer) are hidden by default and can be revealed
with a single user action (expand button or accordion).

**Why this priority**: The current layout mixes answer text and raw source citations, making the answer
hard to read. Separating them improves the primary experience for all users without losing the source
transparency that advanced users want.

**Independent Test**: Submit a question, verify the answer text appears without sources cluttering it,
then expand the sources panel and verify the cited chunks appear.

**Acceptance Scenarios**:

1. **Given** a user submits a question, **When** the answer is returned,
   **Then** the LLM-generated answer text is displayed prominently without source citations visible.
2. **Given** the answer is displayed, **When** the user activates the "Show sources" control,
   **Then** the cited document chunks are revealed in a panel adjacent to or below the answer.
3. **Given** the sources panel is open, **When** the user hides it,
   **Then** only the answer remains visible and layout returns to the default state.

---

### Edge Cases

- What happens when the JSONL file is malformed or missing required fields?
  The system MUST surface a clear error message naming the malformed row and field, and abort evaluation.
- What happens when k is set larger than the number of retrieved documents?
  Recall@k is computed against however many documents were actually returned; no crash.
- What happens when a question returns zero retrieved documents?
  MRR, nDCG, and Recall@k all score 0.0 for that question; no crash.
- What happens when the LLM returns no answer for a Q&A query?
  The answer panel shows a user-visible error message (Principle VII); the sources panel remains hidden.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The application MUST expose a "RAG Evaluation" tab visible only to authenticated GMs.
- **FR-002**: The Evaluation tab MUST allow a GM to specify or upload a JSONL test file where each
  line is a JSON object with fields: `question` (string), `keywords` (list of strings),
  `reference_answer` (string), and `category` (string).
- **FR-003**: For each test question the system MUST compute:
  - **MRR** (Mean Reciprocal Rank) — average reciprocal rank of the first retrieved document
    containing each keyword.
  - **nDCG** (Normalized Discounted Cumulative Gain) — binary relevance nDCG at k across keywords.
  - **Recall@k** — fraction of expected keywords found in the top-k retrieved documents.
- **FR-004**: The value of k MUST default to 10 and MUST be adjustable by the GM via a UI control
  before running evaluation.
- **FR-005**: The Evaluation tab MUST display a per-question results table with columns: Question,
  Category, MRR, nDCG, Recall@k, Keywords Found / Total.
- **FR-006**: The Evaluation tab MUST display aggregate metrics (mean MRR, mean nDCG, mean Recall@k)
  summarising all evaluated questions.
- **FR-007**: Clicking a row in the per-question results table MUST show a detail view with retrieved
  document snippets and a per-keyword rank breakdown. Row selection is handled via the Gradio
  Dataframe native select event — no separate index input or dropdown is required.
- **FR-008**: Both the GM and player Q&A tabs MUST display the LLM-generated answer and cited
  sources in distinct, separately controlled areas of the UI.
- **FR-009**: Cited sources in the Q&A tab MUST be hidden by default and revealed only when the
  user activates a "Show sources" control (e.g., accordion or toggle button).
- **FR-010**: The "Show sources" control MUST be dismissible so the user can re-hide sources after
  viewing them.
- **FR-011**: Evaluation MUST reuse the same retrieval pipeline used by the Q&A tab — no separate
  retrieval implementation.
- **FR-012**: The system MUST log evaluation run start/end and any per-question errors at the
  appropriate level via the `LOG_LEVEL`-controlled logger (Principle VIII).
- **FR-013**: The Evaluation tab MUST display a live progress counter (e.g., "Evaluating question
  12 / 50…") that updates after each question completes, so the GM can see the run is active.

### Key Entities

- **TestQuestion**: Represents one evaluation case — `question` (string), `keywords` (list[str]),
  `reference_answer` (string), `category` (string).
- **RetrievalEvalResult**: Per-question retrieval scores — `mrr` (float), `ndcg` (float),
  `recall_at_k` (float), `keywords_found` (int), `total_keywords` (int), `k` (int).
- **EvalSummary**: Aggregate across all questions — `mean_mrr` (float), `mean_ndcg` (float),
  `mean_recall_at_k` (float), `total_questions` (int).
- **SourceChunk**: A single retrieved document chunk displayed in Q&A sources — `content` (string),
  `source` (string, document identifier), `rank` (int).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A GM can load a JSONL test file and receive per-question MRR, nDCG, and Recall@k scores
  for all questions in a single evaluation run without manual intervention per question.
- **SC-002**: All three metrics (MRR, nDCG, Recall@k) are displayed numerically (to at least 3 decimal
  places) for every evaluated question.
- **SC-003**: Aggregate mean scores across all questions are visible at the end of an evaluation run
  without additional navigation.
- **SC-004**: Non-GM users cannot access or trigger the Evaluation tab (access control verified by
  role, not by obscurity).
- **SC-005**: A Q&A answer is readable without any source citations visible in the default view.
- **SC-006**: A user can reveal cited sources in the Q&A tab with exactly one interaction (one click
  or tap).
- **SC-007**: The Evaluation tab displays a visible placeholder when no test file is loaded (Principle VII).
- **SC-008**: The GM can see a live progress count (current question / total) at all times while
  evaluation is running; the UI does not appear frozen during a multi-question run.

## Clarifications

### Session 2026-06-22

- Q: What does the GM see while evaluation runs across many questions? → A: Live progress counter ("Evaluating question N / total…") updating after each question completes.
- Q: How does the GM select a question row to see the drill-down detail? → A: Click a row in the results table using Gradio's native Dataframe select event.
- Q: Should the sources accordion apply to the player Q&A tab too? → A: Yes — both GM and player Q&A tabs get the sources accordion.

## Assumptions

- The GM role is already defined in the existing `User`/`GameStar` SQLAlchemy models and is
  accessible via the mock auth context; no new role infrastructure is needed.
- The JSONL test file is provided by the GM from their local filesystem or a known path on the server;
  file upload via Gradio's file component is a sufficient loading mechanism.
- The existing RAG retrieval function (`fetch_context` or equivalent) returns a list of document
  objects with a `page_content` attribute, matching the interface used in the provided `eval.py`.
- k=10 is an appropriate default for retrieval depth; GMs who want a different value can adjust it
  per-run via the UI.
- Answer evaluation (LLM-as-judge scoring accuracy/completeness/relevance) is out of scope for this
  feature — only retrieval metrics (MRR, nDCG, Recall@k) are required. The LLM-judge pattern from
  `eval.py` may be added in a future spec.
- Gradio's `gr.Accordion` or `gr.Column` with a visibility toggle is sufficient for the
  collapsible sources panel; no custom JavaScript component is required.
- The JSONL schema matches the `TestQuestion` model from the provided `test.py` context file.
