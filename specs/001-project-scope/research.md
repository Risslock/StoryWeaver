# Research: StoryWeaver — Project Scope & Vision

**Branch**: `001-project-scope` | **Date**: 2026-06-18

Resolves all NEEDS CLARIFICATION items from the Technical Context and open decisions from TECH_STACK.md.

---

## 1. Agent Framework (resolves ADR-005)

**NEEDS CLARIFICATION** in TECH_STACK.md: candidates are Pydantic-AI, LangGraph, lightweight custom.

### Evaluation

| Criterion | Pydantic-AI | LangGraph | Lightweight Custom |
|-----------|-------------|-----------|-------------------|
| Type safety | Full Pydantic v2 | Partial | Self-imposed |
| Model-agnostic | Yes (any OpenAI-compat) | Yes (via adapters) | Yes |
| Ollama support | Native (OpenAI-compat API) | Yes | Yes |
| Tool definition | Decorator-based, typed | More verbose | Manual |
| Multi-agent / handoffs | Agent handoff primitives | State machine graphs | Manual |
| Portfolio clarity | Shows typed agent design | Hides patterns in graph | Most explicit, most code |
| Dependency weight | Minimal (pydantic + httpx) | Heavy (langgraph + langchain) | Zero |
| Digital twin pattern fit | One Agent instance per entity | Node-per-entity awkward | Yes |

### Decision: Pydantic-AI

- **Rationale**: Type-safe agent definitions with built-in tool schemas align with the portfolio goal of demonstrating well-engineered multi-agent design. Pydantic-AI's model-agnostic design works natively with Ollama's OpenAI-compatible API (no adapter code needed), and its lightweight footprint (pydantic v2 + httpx) avoids pulling in the LangChain ecosystem. The per-entity `Agent` instantiation pattern fits digital twins naturally: each Character or NPC gets its own `Agent` instance with its own system prompt, context, and tool set.
- **Alternatives considered**: LangGraph rejected — adds significant complexity (state machine graphs, LangChain dependency) without matching benefits for this domain; the graph abstraction obscures the twin design patterns that are central to the portfolio's value. Lightweight custom rejected — more demonstrability value in Pydantic-AI's structured definitions than in hand-rolled plumbing, while Pydantic-AI still exposes enough internals to show genuine understanding.
- **ADR required**: Write `docs/adr/ADR-005-agent-framework.md` before M2 implementation begins.

---

## 2. Cloud Image Generation Provider (M5+)

**NEEDS CLARIFICATION**: TECH_STACK.md says "TBD (e.g. Replicate / hosted APIs)".

### Evaluation

| Provider | Free tier | SDXL support | API simplicity | Consistency with stack |
|----------|-----------|--------------|----------------|------------------------|
| HuggingFace Inference API | Yes (rate-limited) | SDXL and others | REST, same HF token | Already used for LLM |
| Replicate | Pay-per-run | Excellent | REST (run/poll) | New vendor and token |
| Stability AI API | Pay-per-run | Native | REST | New vendor |

### Decision: HuggingFace Inference API (primary); Replicate as documented alternative

- **Rationale**: Reusing the HuggingFace token and REST surface keeps the cloud provider footprint minimal. The free tier includes SDXL-based models sufficient for portrait and scene generation at solo or small-group scale. The `imagegen` abstraction (`packages/imagegen/interface.py`) makes adding Replicate straightforward if HF rate limits become a bottleneck.
- **Alternatives considered**: Replicate has superior model variety but adds a paid vendor unnecessarily for the portfolio use case. Stability AI is similar in cost profile to Replicate.
- **Final provider selection deferred to M3 ADR**: The abstraction is designed and committed now; the cloud provider is confirmed at M3 after local image gen is in place and quality can be compared.

---

## 3. Campaign Join Code Mechanics

**Context**: FR-012 — campaign join code + display name; no persistent accounts in v1.

### Implementation Pattern

- **Join code format**: 8-character uppercase alphanumeric (e.g., `ASWX3K9P`), generated at Campaign creation via `secrets.token_urlsafe(6)[:8].upper()`. Stored as a unique indexed column on the `campaigns` table.
- **User session**: Gradio `gr.State()` holds a `CampaignSession` dataclass: `{campaign_id: UUID, display_name: str, role: Literal["player", "gm"], ai_available: bool}`. Session state is per-browser-tab (Gradio 4.x session isolation via `gr.State()`).
- **Role assignment**: The user who creates the Campaign receives the GM role (persisted as `Campaign.gm_display_name`). All subsequent joiners with a valid join code receive the Player role. If a joining display name matches `gm_display_name`, the GM role is restored (allows the GM to re-join after a browser refresh).
- **No server-side session persistence**: The `CampaignSession` object lives only in Gradio state for the duration of the browser session. Re-joining after a refresh requires re-entering the join code and display name.
- **Security note**: Join codes are short (8-char) and low-entropy — acceptable for a solo or small-group portfolio context, not a production multi-tenant scenario. A future spec can add expiry or per-code rate limiting.

---

## 4. uv Monorepo Workspace Setup

### Root pyproject.toml structure

```toml
[tool.uv.workspace]
members = ["apps/*", "packages/*"]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.4", "pyright>=1.1", "alembic>=1.13"]
```

### Subpackage pyproject.toml pattern

Each package under `apps/` and `packages/` has its own `pyproject.toml`:

```toml
[project]
name = "storyweaver-<name>"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["storyweaver-core"]  # inter-workspace dep

[tool.uv.sources]
storyweaver-core = { workspace = true }
```

**Install command**: `uv sync` from repo root installs all workspace members and dev dependencies.

---

## 5. Gradio Multi-User Session Management

### Pattern

- `gr.State()` in Gradio 4.x is per-user-session (not shared across browser tabs or concurrent users).
- The app uses a `gr.Blocks()` layout with `gr.State(value=None)` holding the `CampaignSession`.
- On join: state is populated with the resolved `CampaignSession`; role-appropriate tabs are made `visible=True` via a Gradio event handler.
- **Degraded mode**: A persistent `gr.HTML()` banner component is conditionally shown at the top of every page when `CampaignSession.ai_available = False`. All AI-dependent buttons and chat inputs have `interactive=False` set when in degraded mode.
- **Concurrency**: Gradio's default threading model handles concurrent requests; SQLite is configured with WAL mode (`PRAGMA journal_mode=WAL`) to allow concurrent readers alongside writes.

---

## 6. SQLAlchemy ORM Strategy

- SQLAlchemy 2.x with `DeclarativeBase` and fully typed columns (`Mapped[...]`).
- All ORM models live in `packages/core/models.py` — single source of truth for schema.
- DB URL from environment: `sqlite+aiosqlite:///./data/storyweaver.db` (local) or `postgresql+asyncpg://...` (cloud M5+).
- Alembic manages schema migrations, configured at repo root (`alembic.ini`).
- `packages/storage/interface.py` defines a `StorageBackend` ABC wrapping session and connection concerns; the SQLite and Postgres adapters implement it. This satisfies Constitution Principle II (provider abstraction) for the storage layer.