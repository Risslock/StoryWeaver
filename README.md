A# StoryWeaver

> **An AI-powered roleplaying companion** — and a living showcase of spec-driven development, LLM engineering, RAG pipelines, and software architecture.

<div align="center">

*Built for tabletop RPG players. Designed to be read by engineers.*

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Pydantic-AI](https://img.shields.io/badge/Agents-Pydantic--AI-E92063?logo=pydantic)](https://ai.pydantic.dev/)
[![ChromaDB](https://img.shields.io/badge/Vector%20Store-ChromaDB-orange)](https://www.trychroma.com/)
[![Gradio](https://img.shields.io/badge/UI-Gradio-FF7C00?logo=gradio)](https://gradio.app/)
[![uv](https://img.shields.io/badge/Deps-uv-5C3EE8)](https://docs.astral.sh/uv/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)

</div>

---

## What is this project?

StoryWeaver has **two equal purposes**:

### 1. A product — AI roleplaying companion
StoryWeaver helps players and gamemasters run richer tabletop RPG campaigns. Starting with **Earthdawn 4th Edition**, it provides:
- A rules-aware **character builder** that validates decisions against Earthdawn 4E mechanics
- **AI digital twins** — each character and NPC gets its own persistent agent with in-character memory
- **Scene and portrait generation** via local (ComfyUI) or cloud (HuggingFace FLUX.1) image models
- A **living story history** with role-scoped access (GMs see everything, players see public events)
- A **Game Knowledge Q&A** system — ask natural-language questions about rules or campaign lore; cited sources surface in a collapsible accordion
- A **GM-only RAG Evaluation tab** — upload a JSONL test file, run MRR/nDCG/Recall@k retrieval evaluation with live progress, and drill into per-question chunk details

### 2. An engineering portfolio

Every architectural decision in this codebase was made deliberately and is documented. This project demonstrates:

| Topic | Where to look |
|-------|--------------|
| **Spec-driven development** | [`/specs`](specs/) — every feature starts with a spec, plan, and data-model before code |
| **LLM provider abstraction** | [`packages/llm/`](packages/llm/) — swap Ollama → Anthropic → OpenAI with one env var |
| **RAG pipeline engineering** | [`packages/rag/`](packages/rag/) — two-tier retrieval, multi-query expansion, RRF ranking |
| **Agent design with Pydantic-AI** | [`packages/agents/`](packages/agents/) — per-entity digital twins, typed tool schemas |
| **Storage abstraction** | [`packages/storage/`](packages/storage/) — SQLite → Postgres with one env var |
| **Architecture Decision Records** | [`docs/adr/`](docs/adr/) — documented tradeoffs, alternatives rejected |
| **Harness-driven quality** | [`harness/`](harness/) — deterministic eval suites with composite 0–10 scoring |

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph UI["Gradio Browser UI"]
        AUTH["Auth / Account"]
        GM_DASH["GM Dashboard"]
        PL_DASH["Player Dashboard"]
        QA["Knowledge Q&A"]
    end

    subgraph APP["App Layer (apps/web/)"]
        SESSION["Campaign Session"]
        ROUTER["Page Router"]
    end

    subgraph AGENTS["Agent Package (packages/agents/)"]
        GM_AG["GM Agent\n(session planning, world tools)"]
        PL_AG["Player Agent\n(character tools, history)"]
        TWIN["Digital Twin\n(per character / NPC)"]
    end

    subgraph LLM_LAYER["LLM Abstraction (packages/llm/)"]
        IFACE["LLMProvider ABC"]
        OLLAMA["Ollama\n(local default)"]
        ANTHROPIC["Anthropic Claude"]
        OPENAI["OpenAI GPT"]
        HF_LLM["HuggingFace"]
    end

    subgraph RAG_LAYER["RAG Layer (packages/rag/)"]
        KR["KnowledgeRetriever\n(two-tier)"]
        HR["HistoryRetriever"]
        CR["CharacterRetriever"]
        RR["RulesRetriever"]
        CHROMA["ChromaDB\n(persistent local)"]
    end

    subgraph STORAGE["Storage (packages/storage/)"]
        STORE_IF["StorageBackend ABC"]
        SQLITE["SQLite + aiosqlite\n(local default)"]
        PG["Postgres + asyncpg\n(cloud)"]
    end

    subgraph IMGGEN["Image Gen (packages/imagegen/)"]
        IMG_IF["ImageProvider ABC"]
        FLUX["HuggingFace FLUX.1\n(default)"]
        COMFYUI["ComfyUI\n(local)"]
    end

    subgraph RULES["Rules Engine (packages/rules_earthdawn/)"]
        CHAR_BUILD["Character Builder"]
        TALENT_VAL["Talent Validator"]
        CIRCLE_PROG["Circle Progression"]
    end

    UI --> APP
    APP --> AGENTS
    AGENTS --> LLM_LAYER
    AGENTS --> RAG_LAYER
    AGENTS --> IMGGEN
    AGENTS --> STORAGE
    APP --> RULES
    LLM_LAYER --> IFACE
    IFACE --> OLLAMA & ANTHROPIC & OPENAI & HF_LLM
    RAG_LAYER --> CHROMA
    STORAGE --> STORE_IF
    STORE_IF --> SQLITE & PG
    IMGGEN --> IMG_IF
    IMG_IF --> FLUX & COMFYUI
```

---

## Spec-Driven Development Workflow

One of the core engineering practices in StoryWeaver is **spec-first development**: no code is written until the spec, plan, and contracts are reviewed. This mirrors how high-trust engineering teams operate.

```mermaid
flowchart LR
    A["1. Feature Spec\nspec.md\n\nUser stories, acceptance\ncriteria, constraints"] -->
    B["2. Research\nresearch.md\n\nTechnical options,\nlibraries, tradeoffs"] -->
    C["3. Plan\nplan.md\n\nPhases, constitution\ncheck, architecture"] -->
    D["4. Data Model\ndata-model.md\n\nDB schema, Pydantic\nmodels, indexes"] -->
    E["5. Contracts\ncontracts/\n\nUI flows, API surfaces,\nagent tool signatures"] -->
    F["6. Tasks\ntasks.md\n\nDependency-ordered\natomic implementation steps"] -->
    G["7. Implementation\ncode\n\nTDD, harness evals,\nintegration tests"] -->
    H["8. ADR\ndocs/adr/\n\nRecord decisions\nand rejected alternatives"]

    style A fill:#1e3a5f,color:#fff
    style B fill:#1e3a5f,color:#fff
    style C fill:#1e3a5f,color:#fff
    style D fill:#1e3a5f,color:#fff
    style E fill:#1e3a5f,color:#fff
    style F fill:#1e3a5f,color:#fff
    style G fill:#2d6a4f,color:#fff
    style H fill:#5c3d11,color:#fff
```

Each feature directory under [`/specs`](specs/) contains all of these artifacts. The [`CLAUDE.md`](CLAUDE.md) enforces that the spec and plan are the source of truth — when code and spec disagree, the spec wins.

---

## RAG Pipeline: Game Knowledge Q&A

The most technically involved feature is the two-tier RAG system that answers natural-language questions about game rules and campaign lore.

```mermaid
flowchart TD
    subgraph INGEST["Ingestion Pipeline"]
        PDF["PDF / Markdown\nDocument"] -->
        EXTRACT["pymupdf4llm\nText + table extraction\nImage → caption fallback"] -->
        CHUNK["Heading-Based Chunker\nAtomic tables, page-aware\nboundaries"] -->
        ENRICH["LLM Chunk Enrichment\nPydantic-AI structured output\nheadline · summary · topic · access_level"] -->
        EMBED["Embedding\nnomic-embed-text via Ollama\n(OllamaEmbedFn — pre-computed)"] -->
        STORE_VEC["ChromaDB\nTwo-tier collections"]
    end

    subgraph COLLECTIONS["Vector Collections"]
        GLOBAL["knowledge_global\nRulebooks shared across\nall campaigns"]
        CAMPAIGN["knowledge_{id}\nPer-campaign lore\nand notes"]
    end

    subgraph QUERY["Query Pipeline"]
        Q["User Question"] -->
        EXPAND["Multi-Query Expansion\nPydantic-AI → 3 alternative phrasings"] -->
        RETRIEVE["Parallel Retrieval\nGlobal + Campaign collections"] -->
        RRF["Reciprocal Rank Fusion\nRe-ranking across result sets"] -->
        FILTER["Access-Level Filtering\nGM sees all · Player sees public only"] -->
        SYNTH["LLM Answer Synthesis\nCited passages · source references"] -->
        ANS["Answer + Sources accordion\nClean answer in chat · citations on demand"]
    end

    STORE_VEC --> GLOBAL & CAMPAIGN
    GLOBAL & CAMPAIGN --> RETRIEVE

    style INGEST fill:#1a1a2e,color:#eee
    style COLLECTIONS fill:#16213e,color:#eee
    style QUERY fill:#0f3460,color:#eee
```

**Key engineering choices in this pipeline:**

- **Two-tier collections**: rulebooks are indexed once (`knowledge_global`) and shared across all campaigns — no per-campaign re-ingestion cost.
- **Appendage section merging**: before LLM batching, the agentic chunker detects stat-block sections (prose density < `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD`, default 30%) and merges them into the preceding section. This ensures retrieved chunks for attribute values (DEX, STR, Movement Rate) always contain the entity name, not just the numbers. No heading-name configuration required — works across any book structure.
- **LLM enrichment with Pydantic-AI**: every chunk gets structured metadata (headline, summary, topic, access level) validated via a Pydantic model before storage.
- **Multi-query expansion**: the user's question is rewritten into 3 alternative phrasings to improve recall across different terminology.
- **Reciprocal Rank Fusion**: merges results from multiple queries into a single ranked list without requiring score normalization.
- **Access-level filtering**: enforced at retrieval time, not just UI level — player queries never surface GM-only chunks.
- **Dual extraction paths**: `extraction_mode="text"` (default) uses pymupdf4llm with corpus cleaning rules for encoding repair, drop-cap rejoining, image-placeholder stripping, and structural noise detection. `extraction_mode="vision"` renders each PDF page at 144 DPI and passes it to a local Ollama vision model (set `KNOWLEDGE_VISION_MODEL`). Switching extraction mode requires full re-ingestion; `extraction_mode` is stored per-chunk in metadata.
- **Quality gate**: after chunking, stubs < `KNOWLEDGE_MIN_CHUNK_CHARS` (default 150) are merged into adjacent chunks, and giants > `KNOWLEDGE_MAX_CHUNK_CHARS` (default 15 000) are re-split. This runs on both text and vision paths.

---

## Digital Twin Architecture

Every character and NPC gets its own scoped AI agent — a "digital twin" — that knows only what that entity should know.

```mermaid
flowchart TD
    subgraph SESSION["Campaign Session (role-scoped)"]
        GM_ROLE["GM Role"]
        PL_ROLE["Player Role"]
    end

    subgraph TWINS["Digital Twins (packages/agents/twin/)"]
        CHAR_TWIN["Character Twin\nPlayer's own character\nPersonality + backstory + sheet"]
        NPC_TWIN["NPC Twin\nGM-controlled\nOnly GM can converse"]
    end

    subgraph TWIN_CONTEXT["Per-Twin Context Window"]
        SYS["System prompt\n(sheet + personality)"]
        RAG_CTX["RAG context\n(relevant history + rules)"]
        CONV["Conversation history\n(last N turns)"]
    end

    subgraph TOOLS["Role-Scoped Tools"]
        PL_TOOLS["Player tools\nget_character_sheet\nlog_public_event\nask_knowledge_qa"]
        GM_TOOLS["GM tools\nget_all_events\nplan_session\nmanage_npc\nask_knowledge_qa"]
    end

    GM_ROLE --> NPC_TWIN
    PL_ROLE --> CHAR_TWIN
    CHAR_TWIN & NPC_TWIN --> TWIN_CONTEXT
    TWIN_CONTEXT --> LLM_CALL["LLMProvider.generate()"]
    GM_ROLE --> GM_TOOLS
    PL_ROLE --> PL_TOOLS
```

Each twin carries its own system prompt, has access only to its entity's context, and uses the RAG layer for semantic recall before falling back to SQL. The `LLMProvider` abstraction means the same twin works with Ollama locally or any cloud provider.

---

## Provider Abstraction Pattern

A core design principle: **switch any AI provider via `.env` — no code changes required.**

```mermaid
flowchart LR
    subgraph CODE["Application Code"]
        AGENT["Agent / Twin"]
        IMG_CODE["Image Gen code"]
        STORE_CODE["Storage code"]
    end

    subgraph ABCS["Abstract Base Classes"]
        LLM_ABC["LLMProvider ABC\npackages/llm/interface.py"]
        IMG_ABC["ImageProvider ABC\npackages/imagegen/interface.py"]
        STORE_ABC["StorageBackend ABC\npackages/storage/interface.py"]
    end

    subgraph IMPLS["Concrete Implementations\n(selected via env var)"]
        direction TB
        OLLAMA_I["OllamaProvider\nLLM_PROVIDER=ollama"]
        ANT_I["AnthropicProvider\nLLM_PROVIDER=anthropic"]
        OAI_I["OpenAIProvider\nLLM_PROVIDER=openai"]
        HF_I["HuggingFaceProvider\nLLM_PROVIDER=huggingface"]
        FLUX_I["HuggingFaceImageProvider\nIMAGE_PROVIDER=huggingface"]
        COMFY_I["ComfyUIProvider\nIMAGE_PROVIDER=comfyui"]
        SQ_I["SQLiteBackend\nsqlite+aiosqlite://"]
        PG_I["PostgresBackend\npostgresql+asyncpg://"]
    end

    AGENT --> LLM_ABC
    IMG_CODE --> IMG_ABC
    STORE_CODE --> STORE_ABC
    LLM_ABC --> OLLAMA_I & ANT_I & OAI_I & HF_I
    IMG_ABC --> FLUX_I & COMFY_I
    STORE_ABC --> SQ_I & PG_I
```

---

## Disclaimer

StoryWeaver is an **unofficial, fan-made companion tool**. *Earthdawn* is a trademark of **FASA Corporation / FASA Games**, and all related rules, settings, and intellectual property belong to their respective owners. This project does not redistribute copyrighted rulebook text, art, or proprietary content. It implements game *mechanics* as a tool to support legitimate play, not as a replacement for the books.

---

## Implementation Status

| Milestone | Status | What it delivers |
|-----------|--------|-----------------|
| M0 — Scaffolding | ✅ Complete | uv workspace, Docker Compose, ruff/pyright, `.env.example` |
| M1 — Character creation | ✅ Complete | Guided Earthdawn 4E builder, character sheet, validation |
| M2 — Digital twins | ✅ Complete | AI twin per character/NPC (local Ollama), role-based tools, degraded mode |
| M3 — Image generation | ✅ Complete | HuggingFace FLUX.1 (default) + ComfyUI (local), graceful error handling |
| M4 — Story history + GM planning | ✅ Complete | Persistent timeline, role-scoped events, session planning agent |
| M4.5 — RAG layer | ✅ Complete | ChromaDB history/character/rules indexes; twin falls back to SQL when unavailable |
| M5 — Cloud providers | ✅ Complete | Anthropic, OpenAI, HuggingFace LLM providers; Postgres adapter |
| M6 — Auth & Admin UI | ✅ Complete | GM registration/login, campaign dashboard, join codes, player rejoin |
| M7 — Auth Reboot | ✅ Complete | Auth-first for all users, post-login hub, `user_id`-linked player records |
| M8 — Game Knowledge Q&A | ✅ Complete | Two-tier RAG, PDF→Markdown ingestion, LLM enrichment, RRF ranking, access filtering |
| M9 — RAG Evaluation & Q&A UX | ✅ Complete | GM-only evaluation tab (MRR/nDCG/Recall@k), live progress, drill-down detail; sources accordion in Q&A |
| M10 — Contextual retrieval & breadcrumbs | ✅ Complete | Per-category benchmark output (direct_fact/comparison/holistic/numeric/relationship); breadcrumb-enriched chunks (heading path prefixed to every chunk); opt-in contextual LLM summaries per chunk; `source_type` metadata tag on every stored chunk; `IngestionConfig` as the unified ingestion API. Baseline (agentic chunker, breadcrumbs on, summaries off, 118 questions): MRR 0.550 · nDCG 0.627 · Recall@10 0.902. **Note**: enabling breadcrumbs or contextual summaries on an existing index requires full re-ingestion. |

---

## Tech Stack

| Area | Choice | Notes |
|------|--------|-------|
| Language | **Python 3.11+** | |
| UI | **Gradio 4.x** | Browser-friendly, role-scoped tabs |
| Dependency management | **uv** | Workspace monorepo in root `pyproject.toml` |
| Agent framework | **Pydantic-AI** | Per-entity agents, typed tool schemas — see [ADR-005](docs/adr/ADR-005-agent-framework.md) |
| LLM (local) | **Ollama** | Default; OpenAI-compatible REST API |
| LLM (cloud) | **Anthropic · OpenAI · HuggingFace** | Via `LLM_PROVIDER` env var |
| Embeddings | **`nomic-embed-text` via Ollama** | Custom `OllamaEmbedFn`; pre-computed before ChromaDB calls on both ingestion and retrieval paths |
| Vector store (local) | **ChromaDB** | File-backed persistent store |
| Vector store (cloud) | **pgvector** | Postgres extension (wiring planned) |
| PDF extraction | **pymupdf4llm** | Tables → GFM Markdown; images → caption fallback |
| Image gen (default) | **HuggingFace Inference API** | Free tier — FLUX.1-schnell |
| Image gen (local) | **ComfyUI** | Requires local ComfyUI server |
| DB (local) | **SQLite** | WAL mode; via SQLAlchemy 2.x + aiosqlite |
| DB (cloud) | **Postgres** | Via asyncpg + SQLAlchemy 2.x |
| Containers | **Docker + Docker Compose** | Local and cloud compose files in `deploy/compose/` |
| Testing | **pytest** + **harness** | `tests/` for integration; `harness/` for deterministic agent evals |
| Quality | **ruff** + **pyright** | Linting and strict type checking |

---

## Repository Layout

```
StoryWeaver/
├── apps/
│   └── web/                        # Gradio UI entry point
│       ├── app.py                  # App factory — launch with: uv run python app.py
│       ├── pages/
│       │   ├── auth.py             # Sign In / Create Account tabs
│       │   ├── player/             # Player views: join, character, twin chat, history
│       │   └── gm/                 # GM views: campaigns, NPCs, history, world notes, plans, RAG eval
│       ├── services/
│       │   ├── auth.py             # SHA-256 hashing, validate_user, register_user
│       │   ├── db.py               # SQLiteBackend singleton
│       │   ├── eval.py             # run_evaluation() — JSONL → retrieval metrics
│       │   └── knowledge.py        # ask_question(), submit_document(), check_duplicate()
│       └── components/             # Shared Gradio components
├── packages/
│   ├── core/                       # Shared ORM models, Pydantic schemas, config, errors
│   ├── rules_earthdawn/            # Earthdawn 4E rules engine (isolated — add systems here)
│   ├── agents/                     # Role agents + digital twins (Pydantic-AI)
│   │   ├── twin/                   # Digital twin (Character + NPC)
│   │   ├── player_agent/           # Player role tools
│   │   └── gm_agent/               # GM role tools + session planning
│   ├── llm/                        # LLM provider abstraction
│   │   └── providers/              # ollama, anthropic, openai, huggingface
│   ├── imagegen/                   # Image generation abstraction
│   │   └── providers/              # huggingface, comfyui
│   ├── rag/                        # RAG retrieval layer
│   │   ├── knowledge/              # Two-tier Q&A (ingestor, retriever, enricher)
│   │   ├── history/                # Campaign event index
│   │   ├── character/              # Character/NPC profile index
│   │   └── rules/                  # Earthdawn mechanics index
│   ├── storage/                    # DB backend abstraction
│   │   ├── sqlite/                 # SQLite adapter (local default, WAL mode)
│   │   └── postgres/               # Postgres adapter (cloud)
│   └── story/                      # Story event + session CRUD
├── harness/                        # Deterministic agent/tool eval suites
│   ├── scenarios/                  # YAML fixtures per tool/agent
│   ├── scoring/                    # rubrics.py — composite 0–10 scoring
│   ├── knowledge_qa/               # RAG retrieval metric tests (test_evaluator.py, test_eval_service.py)
│   └── runner.py                   # Dispatch runner
├── tests/
│   └── integration/                # pytest integration tests (per user story)
├── specs/                          # Spec-driven development artifacts
│   ├── 001-project-scope/          # spec · plan · data-model · contracts · tasks
│   ├── 002-auth-admin-ui/
│   ├── 003-demo-readiness-polish/
│   ├── 004-auth-admin-reboot/
│   ├── 005-rag-qa-system/
│   └── 006-rag-eval-qa-ux/
├── docs/adr/                       # Architecture Decision Records
├── deploy/
│   ├── docker/                     # Dockerfile.web, Dockerfile.ollama
│   └── compose/                    # docker-compose.local.yml, docker-compose.cloud.yml
├── pyproject.toml                  # uv workspace + ruff + pyright config
└── .env.example                    # All required env vars documented
```

---

## Getting Started

**Prerequisites**: Python 3.11+, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com)

```bash
# 1. Clone
git clone https://github.com/Risslock/StoryWeaver.git
cd StoryWeaver

# 2. Install all workspace packages
uv sync

# 3. Pull required local models
ollama pull llama3.1
ollama pull nomic-embed-text   # required for Knowledge Q&A

# 4. Configure
cp .env.example .env
# Default .env works for local dev — SQLite + Ollama, no changes needed

# 5. Run database migrations
uv run alembic upgrade head

# 6. Launch
cd apps/web && uv run python app.py
# Opens at http://localhost:7860
# Use "Create Account" → "Sign In" → choose GM or Player path
```

### Docker (local full stack)

```bash
docker compose -f deploy/compose/docker-compose.local.yml up
# Gradio + Ollama + ChromaDB + SQLite volume — everything in one command
```

### Docker (cloud stack)

```bash
# Requires DATABASE_URL, LLM_PROVIDER, LLM_API_KEY in environment
docker compose -f deploy/compose/docker-compose.cloud.yml up
```

---

## Configuration

All providers switch via `.env` — no code changes.

```dotenv
# LLM provider: ollama | anthropic | openai | huggingface
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1

# Cloud LLM (uncomment one)
# LLM_PROVIDER=anthropic
# LLM_API_KEY=sk-ant-...

# LLM_PROVIDER=openai
# LLM_API_KEY=sk-...

# Image generation: huggingface | comfyui
IMAGE_PROVIDER=huggingface
HF_API_KEY=
HF_IMAGE_MODEL=black-forest-labs/FLUX.1-schnell

# Database: sqlite (local) or postgres (cloud)
DATABASE_URL=sqlite+aiosqlite:///./data/storyweaver.db
# DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/storyweaver

MAX_TWIN_TURNS=20

# Agentic chunker: sections below this prose fraction are merged into the preceding section
# so stat blocks retain entity context (race name + attributes in the same chunk)
KNOWLEDGE_AGENTIC_PROSE_THRESHOLD=0.3

# Extraction mode: "text" (default, pymupdf4llm) or "vision" (local Ollama vision model).
# Changing this requires a full re-ingestion — existing chunks retain their original extraction_mode.
# KNOWLEDGE_EXTRACTION_MODE=text

# Vision extraction (only used when extraction_mode="vision"):
KNOWLEDGE_VISION_MODEL=minicpm-v            # required when using vision path
KNOWLEDGE_VISION_TIMEOUT_SECS=120          # per-page HTTP timeout
KNOWLEDGE_VISION_MAX_RETRIES=1             # retry attempts before IngestionAbortError

# Quality gate (chunk size bounds, applied after chunking):
KNOWLEDGE_MIN_CHUNK_CHARS=150              # stubs below this are merged into adjacent chunk
KNOWLEDGE_MAX_CHUNK_CHARS=15000            # giants above this are re-split via the active chunker

# Logging level (DEBUG surfaces RAG eval run start/end and per-question errors)
LOG_LEVEL=INFO
```

---

## Running Tests

```bash
# All integration tests
uv run pytest tests/integration/ -v

# Per feature
uv run pytest tests/integration/test_character_creation.py -v
uv run pytest tests/integration/test_role_access.py -v
uv run pytest tests/integration/test_story_history.py -v

# Harness eval runner (deterministic agent/tool scenarios)
uv run python harness/runner.py --all
uv run python harness/runner.py --dir harness/scenarios/gm_agent/

# Lint + type check
uv run ruff check .
uv run pyright
```

---

## Roadmap

### Completed
- [x] M0 — Monorepo scaffolding, config/abstraction layers, harness skeleton
- [x] M1 — Earthdawn 4E character creation (rules engine + Gradio builder)
- [x] M2 — Digital twins (per-character/NPC agents, role-based tools, degraded mode)
- [x] M3 — Image generation (HuggingFace FLUX.1 + ComfyUI)
- [x] M4 — Story history + GM session planning
- [x] M4.5 — RAG layer (history/character/rules ChromaDB indexes)
- [x] M5 — Cloud providers (Anthropic, OpenAI, HuggingFace; Postgres adapter)
- [x] M6 — Auth & campaign admin UI
- [x] M7 — Auth-first for all users (no anonymous access)
- [x] M8 — Game Knowledge Q&A (two-tier RAG, PDF ingestion, LLM enrichment, RRF)
- [x] M9 — RAG Evaluation tab + Q&A sources accordion (MRR/nDCG/Recall@k, drill-down, GM-only)
- [x] M10 — Contextual retrieval & breadcrumbs (per-category benchmarking, breadcrumb injection, opt-in contextual summaries, `source_type` metadata, `IngestionConfig` API)

### Planned
- [ ] **System-agnostic core** — second rule system beyond Earthdawn
- [ ] **RAG auto-indexing** — index story events and character updates at write time
- [ ] **pgvector wiring** — cloud vector store via Postgres extension
- [ ] **Agentic character creation** — conversational builder instead of forms
- [ ] **MCP integration** — expose StoryWeaver as MCP tools for external agent workflows
- [ ] **Places model** — cities, roads, ruins as first-class entities with history and AI descriptions

---

## Contributing

1. Open a **spec** in `/specs/<feature-name>/` — define intent before touching code.
2. Write **harness scenarios** for any new agent or tool behaviour.
3. Implement against the spec; keep packages isolated.
4. Ensure `pytest`, harness, `ruff`, and `pyright` all pass.
5. Update this README and add an ADR for any non-trivial architectural decision.

---

## License

StoryWeaver is released under the **Apache License 2.0**. See [LICENSE](LICENSE).

The project license covers StoryWeaver's own code only — it does not extend to Earthdawn or FASA intellectual property.

---

*StoryWeaver — weave your story.*