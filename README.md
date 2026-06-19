# StoryWeaver

> An AI-assisted companion for tabletop role-playing games — starting with **Earthdawn (4th Edition)** and growing into a system-agnostic platform.

StoryWeaver helps players and gamemasters create characters, give every character and NPC an **AI digital twin** for dialogue and behaviour, generate **character and scene imagery**, and keep a living **story history** of the campaign. It runs **locally on your machine** or **in the cloud**, fully dockerized.

> [!IMPORTANT]
> **This document is the source of truth.** StoryWeaver follows *spec-driven development* — the README and the `/specs` directory define intent before code is written. When code and spec disagree, the spec wins. Update this file deliberately; it is the guiding point for all future development.

---

## Disclaimer

StoryWeaver is an **unofficial, fan-made companion tool**. *Earthdawn* is a trademark of **FASA Corporation / FASA Games**, and all related rules, settings, and intellectual property belong to their respective owners. This project:

- Does **not** redistribute copyrighted rulebook text, art, or proprietary content.
- Assumes users own the official rulebooks required to play.
- Implements game *mechanics* as a tool to support legitimate play, not as a replacement for the books.

---

## Current Status (as of Phase 10 completion)

All milestones M0–M5 are **implemented and passing integration tests**.

| Milestone | Status | What it delivers |
|-----------|--------|-----------------|
| M0 — Scaffolding | ✅ Complete | uv workspace, Docker Compose, ruff/pyright, `.env.example` |
| M1 — Character creation | ✅ Complete | Guided Earthdawn 4E builder, character sheet, validation |
| M2 — Digital twins | ✅ Complete | AI twin per character/NPC (local Ollama), role-based tools, degraded mode |
| M3 — Image generation | ✅ Complete | HuggingFace (default) + ComfyUI (local), graceful error handling |
| M4 — Story history + GM planning | ✅ Complete | Persistent timeline, role-scoped events, session planning agent |
| M4.5 — RAG layer | ✅ Implemented | ChromaDB history/character/rules indexes; twin falls back to SQL when unavailable |
| M5 — Cloud providers | ✅ Implemented | Anthropic, OpenAI, HuggingFace LLM providers; Postgres adapter; harness runner complete |
| M6 — Auth & Admin UI | ✅ Implemented | GM account registration/login, campaign admin dashboard, join code sharing, player rejoin, character/NPC upsert semantics |

### Known limitations

- **No real-time sync**: shared campaigns use refresh-based sync only (by design for v1).
- **RAG indexes are not auto-populated**: story events must be indexed by calling `HistoryRetriever.index_event()` at write time; the twin falls back to SQL if the index is empty.
- **No cloud vector store**: pgvector integration is stubbed but not wired into the RAG layer (Postgres storage adapter is ready; pgvector queries require a future migration).
- **Twin dialogue eval**: `harness/scenarios/twin_dialogue/` scenarios are SKIP in the automated runner — they require a live LLM and are scored via `harness/scoring/rubrics.py` instead.
- **Docker end-to-end validation** requires a Docker host; the compose files are ready but automated CI validation against a live stack has not been run.
- **No password reset**: GM account password reset is out of scope for this phase.
- **No join code rotation**: once a join code is set at campaign creation, it cannot be changed.
- **Player passwords**: players join via campaign name + join code + player name; they still need a StoryWeaver account to access the authenticated main app. Per-player passwords (separate from the account password) are out of scope.
- **M7 — Beyond Earthdawn**: system-agnostic core and second rule system are not yet implemented.

---

## Features

### Implemented (v1 — Earthdawn 4E)

- **Character creation** — guided, rules-aware builder (Disciplines, Talents, attributes, circle progression).
- **AI digital twins** — each character and NPC gets a persistent agent for in-character dialogue grounded in their sheet, personality, and story history.
- **Image generation** — character portraits and GM scene illustrations via HuggingFace (free tier) or ComfyUI (local).
- **Story history** — persistent, role-scoped timeline: GM sees all events, players see only public ones.
- **GM session planning** — AI-generated session plans that reference past events and open plot threads.
- **Degraded mode** — app starts and remains functional (character sheets, history, navigation) when the AI provider is unavailable.
- **RAG layer** — ChromaDB-backed history, character, and rules indexes; twin recall falls back to SQL when RAG is unavailable.
- **Cloud LLM providers** — Anthropic, OpenAI, and HuggingFace providers behind the same `LLMProvider` interface; switch via `LLM_PROVIDER` env var.
- **Postgres storage** — async Postgres adapter behind the same `StorageBackend` interface; switch via `DATABASE_URL`.
- **GM authentication** — bcrypt account system; register at `/register`, log in at `/` via Gradio built-in auth.
- **Campaign admin dashboard** — GMs see all their campaigns, create new ones, and navigate to campaign detail with copyable join code.
- **Player rejoin** — players enter campaign name + join code + player name; character state is automatically restored across sessions.
- **Character/NPC upsert** — creating a character or NPC with a name that matches an existing one (case-insensitive, per campaign) updates the record instead of creating a duplicate.

### Planned

- Additional rule systems beyond Earthdawn (system-agnostic core).
- RAG auto-indexing on event write.
- pgvector cloud vector store wiring.
- Cross-device sync between local and cloud play.
- Richer GM tooling (encounter building, initiative, secret notes).

---

## Roles & Agents

| Role | Focus | Example tools |
|------|-------|---------------|
| **Player** | Their own character(s) | Character builder, personal digital twin, story history (public only) |
| **Gamemaster** | The world & NPCs | NPC digital twins, scene generation, private events, session planning, full history |

Each character/NPC digital twin is its own scoped agent — it sees only what that entity should know.

---

## Architecture

```mermaid
flowchart TD
    UI["Gradio UI (browser)"] --> APP["StoryWeaver App Layer"]
    APP --> AG["Agent Orchestrator<br/>(role + twin agents)"]
    APP --> RULES["Rules Engine<br/>(Earthdawn 4E)"]
    APP --> STORY["Story History"]
    AG --> LLM["LLM Provider Abstraction"]
    AG --> IMG["Image Gen Abstraction"]
    AG --> RAG["RAG / Retrieval Layer"]
    RULES --> RAG
    STORY --> RAG
    RAG --> VECSTORE["Vector Store<br/>(Chroma · pgvector)"]
    VECSTORE --> RULESIDX["Rules Index<br/>(mechanics & tables)"]
    VECSTORE --> HISTIDX["Campaign History Index<br/>(sessions · NPCs · threads)"]
    VECSTORE --> CHARIDX["Character Index<br/>(sheets · backstory · decisions)"]
    LLM --> OLLAMA["Ollama / llama.cpp (local)"]
    LLM --> CLOUDLLM["Cloud APIs<br/>(Anthropic · OpenAI · HuggingFace)"]
    IMG --> LOCALIMG["Stable Diffusion / ComfyUI (local)"]
    IMG --> CLOUDIMG["HuggingFace Inference API"]
    APP --> STORAGE["Storage Backend"]
    STORAGE --> SQLITE["SQLite (local)"]
    STORAGE --> PG["Postgres (cloud)"]
```

### Key design decisions

- **Provider-agnostic AI.** Thin abstraction layers wrap all LLM, image, and storage calls. Switch providers via `.env` — no code changes required.
- **RAG-augmented context.** Three purpose-built retrieval indexes (rules, campaign history, character data) feed relevant chunks into agent prompts. Falls back to SQL when ChromaDB is unavailable.
- **Local-first, cloud-optional.** SQLite + Ollama + ChromaDB + ComfyUI are defaults. Postgres + cloud LLMs are opt-in upgrades.
- **Rules engine is isolated.** Earthdawn 4E lives in `packages/rules_earthdawn/` so additional systems can be added later.
- **Harness-driven quality.** `/harness` holds deterministic eval suites for every agent and tool; they run as regression tests.

---

## Tech Stack

| Area | Choice | Notes |
|------|--------|-------|
| Language | **Python 3.11+** | |
| UI | **Gradio 4.x** | Browser-friendly, role-scoped tabs |
| Dependency management | **uv** | Workspace config in root `pyproject.toml` |
| LLM (local) | **Ollama** | Default; OpenAI-compat API |
| LLM (cloud) | **Anthropic · OpenAI · HuggingFace** | Via `LLM_PROVIDER` env var |
| Embeddings (local) | **`nomic-embed-text` via Ollama** | |
| Vector store (local) | **ChromaDB** | File-backed |
| Vector store (cloud) | **pgvector** | Postgres extension (wiring planned) |
| Image gen (default) | **HuggingFace Inference API** | Free tier — `FLUX.1-schnell` |
| Image gen (local) | **ComfyUI** | Requires local ComfyUI server |
| Agent framework | **Pydantic-AI** | See `docs/adr/ADR-005-agent-framework.md` |
| DB (local) | **SQLite** | WAL mode; via SQLAlchemy 2.x + aiosqlite |
| DB (cloud) | **Postgres** | Via asyncpg + SQLAlchemy 2.x |
| Containers | **Docker + Docker Compose** | Local and cloud compose files in `deploy/compose/` |
| Testing | **pytest** + **harness** | `tests/` for integration; `harness/` for agent evals |

---

## Repository Layout

```
StoryWeaver/
├── apps/
│   └── web/                        # Gradio UI entry point
│       ├── main.py                 # FastAPI ASGI entry point (uvicorn main:app)
│       ├── app.py                  # Gradio app factory, session routing
│       ├── services/
│       │   └── auth.py             # Password hashing, auth callable factory, register_user
│       ├── pages/
│       │   ├── landing.py          # Player campaign join (campaign name + join code)
│       │   ├── registration.py     # Unauthenticated registration companion at /register
│       │   ├── admin/
│       │   │   └── campaigns.py    # GM campaign dashboard + campaign detail (join code)
│       │   ├── player/             # Player views (character, twin chat, history)
│       │   └── gm/                 # GM views (NPCs, characters, history, world notes, session plan)
│       └── components/             # Shared Gradio components (banner, image display)
├── packages/
│   ├── core/                       # Shared ORM models, Pydantic schemas, config, errors
│   ├── rules_earthdawn/            # Earthdawn 4E rules engine (isolated)
│   ├── agents/                     # Role agents + digital twins (Pydantic-AI)
│   │   ├── twin/                   # Digital twin (Character + NPC)
│   │   ├── player_agent/           # Player role tools
│   │   └── gm_agent/               # GM role tools + session planning
│   ├── llm/                        # LLM provider abstraction
│   │   └── providers/              # ollama, anthropic, openai, huggingface
│   ├── imagegen/                   # Image generation abstraction
│   │   └── providers/              # huggingface, comfyui
│   ├── rag/                        # RAG retrieval layer (ChromaDB)
│   │   ├── history/                # Campaign event index
│   │   ├── character/              # Character/NPC profile index
│   │   └── rules/                  # Earthdawn mechanics index
│   ├── storage/                    # DB backend abstraction
│   │   ├── sqlite/                 # SQLite adapter (local default, WAL mode)
│   │   └── postgres/               # Postgres adapter (cloud M5+)
│   └── story/                      # Story event + session CRUD
├── harness/                        # Deterministic agent/tool eval suites
│   ├── scenarios/                  # YAML fixtures per tool/agent
│   ├── scoring/                    # rubrics.py — composite 0–10 scoring
│   └── runner.py                   # Dispatch runner (all scenario types)
├── tests/
│   └── integration/                # pytest integration tests (per user story)
├── docs/adr/                       # Architecture Decision Records
├── deploy/
│   ├── docker/                     # Dockerfile.web, Dockerfile.ollama
│   └── compose/                    # docker-compose.local.yml, docker-compose.cloud.yml
├── specs/001-project-scope/        # Spec, plan, data-model, contracts, tasks
├── pyproject.toml                  # uv workspace + ruff + pyright config
└── .env.example                    # All required env vars documented
```

---

## Getting Started (local development)

**Prerequisites**: Python 3.11+, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com)

```bash
# 1. Clone
git clone https://github.com/Risslock/StoryWeaver.git
cd StoryWeaver

# 2. Install all workspace packages
uv sync

# 3. Pull a local model
ollama pull llama3.1

# 4. Configure
cp .env.example .env
# Default .env works for local dev — SQLite + Ollama, no changes needed

# 5. Run database migrations
uv run alembic upgrade head

# 6. Start the app (FastAPI + uvicorn entry point)
cd apps/web && uv run uvicorn main:app --port 7860 --reload
# Main app:        http://localhost:7860   (sign-in required)
# Registration:    http://localhost:7860/register  (create a GM account first)
```

### Containerized (local Docker stack)

```bash
docker compose -f deploy/compose/docker-compose.local.yml up
# Full local stack: Gradio + Ollama + ChromaDB + SQLite volume
```

### Containerized (cloud stack)

```bash
# Requires: DATABASE_URL, LLM_PROVIDER, LLM_API_KEY in environment
docker compose -f deploy/compose/docker-compose.cloud.yml up
# Cloud stack: Gradio + Postgres/pgvector + cloud LLM
```

---

## Configuration

All providers are switched via environment variables — **no code changes required**.

```dotenv
# --- LLM provider --- (ollama | anthropic | openai | huggingface)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1

# Cloud LLM (uncomment to switch)
# LLM_PROVIDER=anthropic
# LLM_API_KEY=sk-ant-...

# LLM_PROVIDER=openai
# LLM_API_KEY=sk-...

# LLM_PROVIDER=huggingface
# HF_API_KEY=hf_...

# --- Image generation --- (huggingface | comfyui)
IMAGE_PROVIDER=huggingface
HF_API_KEY=               # required for HuggingFace image gen
HF_IMAGE_MODEL=black-forest-labs/FLUX.1-schnell

# --- Database ---
DATABASE_URL=sqlite+aiosqlite:///./data/storyweaver.db
# DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/storyweaver

# --- App ---
MAX_TWIN_TURNS=20
```

---

## Running Tests

```bash
# All integration tests
uv run pytest tests/integration/ -v

# Specific user story
uv run pytest tests/integration/test_character_creation.py -v
uv run pytest tests/integration/test_role_access.py -v
uv run pytest tests/integration/test_story_history.py -v
uv run pytest tests/integration/test_image_generation.py -v
uv run pytest tests/integration/test_shared_campaign.py -v
uv run pytest tests/integration/test_session_planning.py -v

# Harness scenario runner (all deterministic scenario types)
uv run python harness/runner.py --all

# Run a specific scenario directory
uv run python harness/runner.py --dir harness/scenarios/gm_agent/

# Lint and type check
uv run ruff check .
uv run pyright
```

---

## Roadmap

### Completed

- [x] **M0 — Foundations**: monorepo scaffolding, config/abstraction layers, harness skeleton.
- [x] **M1 — Earthdawn 4E character creation**: rules engine + Gradio builder.
- [x] **M2 — Digital twins**: per-character/NPC agents (local Ollama), role-based tools, degraded mode.
- [x] **M3 — Image generation**: character & scene generation (HuggingFace free tier + ComfyUI).
- [x] **M4 — Story history + GM session planning**: persistent timeline, role-scoped events.
- [x] **M4.5 — RAG layer**: history/character/rules ChromaDB indexes; twin semantic recall with SQL fallback.
- [x] **M5 — Cloud providers**: Anthropic, OpenAI, HuggingFace LLM providers; Postgres storage adapter; harness runner complete.

### Planned (unordered)

- [ ] **Beyond Earthdawn**: system-agnostic core, second rule system.
- [ ] **RAG auto-indexing**: automatically index story events and character updates at write time — no manual calls to `index_event()` required.
- [ ] **Authentication & admin UI**: Gradio-based login for GM admin privileges; recover and continue old campaigns from the UI without manual DB access.
- [ ] **Places model**: cities, towns, roads, kaerns, ruins — location entities with their own events, history, and AI-generated descriptions.
- [ ] **UI/UX improvements**:
  - Agentic character creation (conversational builder instead of form-driven).
  - One-button quick NPC creation.
  - Story text dump for auto-event generation (import from Obsidian Portal, Discord, or local GM notes).
  - Remove unused UI surfaces and streamline the GM/player flows.
- [ ] **Prompt improvements**: tuned system prompts for more in-character, coherent twin dialogue and better image-generation descriptions.
- [ ] **Tools & MCP integration**: expose StoryWeaver capabilities as MCP tools for richer agentic workflows and external integrations.

---

## Contributing

1. Open or update a **spec** in `/specs` describing the change.
2. Write or extend **harness** scenarios for any agent/tool behaviour.
3. Implement against the spec; keep packages isolated.
4. Ensure `pytest` and harness scenarios pass; `ruff` and `pyright` report no errors.
5. Update `README.md` to reflect the current implemented state before marking a milestone complete.

---

## License

StoryWeaver is released under the **Apache License 2.0**. See [LICENSE](LICENSE) for the full text.

The project license covers *StoryWeaver's own code only* — it does not extend to Earthdawn/FASA intellectual property (see Disclaimer above).

---

*StoryWeaver — weave your story.*
