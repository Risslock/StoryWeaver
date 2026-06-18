# Implementation Plan: StoryWeaver — Project Scope & Vision

**Branch**: `001-project-scope` | **Date**: 2026-06-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-project-scope/spec.md`

## Summary

StoryWeaver is a local-first, monorepo Python 3.11+ / Gradio AI-assisted narrative companion for tabletop RPGs. This plan covers the full project architecture: monorepo scaffolding (M0), Earthdawn 4E character creation (M1), digital twins via Pydantic-AI agents (M2), image generation (M3), story history + RAG (M4/M4.5), and cloud/sync (M5). All AI and storage providers are abstracted behind thin interfaces switchable via environment variables.

## Technical Context

**Language/Version**: Python 3.11+; optional Rust/C++ extensions via `packages/<name>/native/` (optional to build, Python fallback required)

**Primary Dependencies**: Gradio 4.x (UI), uv (dependency management), Pydantic-AI (agent framework — see research.md ADR-005), Ollama (local LLM + embeddings), ChromaDB (local vector store), SQLite + SQLAlchemy 2.x (local DB), Docker + Docker Compose (deployment)

**Storage**: SQLite (local default, via SQLAlchemy ORM) / Postgres (cloud M5+, same ORM models); ChromaDB (local vector store) / pgvector (cloud M5+)

**Testing**: pytest for unit and integration tests; `/harness` for agent/tool evals with deterministic scoring

**Target Platform**: Linux (containerized via Docker); developer machine (Windows/macOS/Linux) via uv or Docker

**Project Type**: Local-first web application (Gradio), containerized monorepo

**Performance Goals**: Story history load ≤ 5s for ≥5 sessions / ≥20 events (SC-008); twin response quality ≥ 8/10 in-character by human review (SC-006); image quality ≥ 7/10 by human review (SC-007)

**Constraints**: No cloud service required at runtime (local-first); provider-swap via env vars only; refresh-based sync in v1 (no real-time); no persistent user accounts in v1 (join code + display name)

**Scale/Scope**: Solo or small-group (≤10 players per campaign); single developer portfolio project; 7 milestones M0–M6

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Development | ✅ PASS | Plan written before code; spec exists at `specs/001-project-scope/spec.md` |
| II. Provider Abstraction | ✅ PASS | `packages/llm/`, `packages/imagegen/`, `packages/rag/`, `packages/storage/` defined as abstraction layers |
| III. Package Isolation | ✅ PASS | Each package has a declared domain; `rules_earthdawn/` isolated from core; no packages exist solely for organization |
| IV. Local-First, Cloud-Optional | ✅ PASS | Ollama + ChromaDB + SQLite + ComfyUI are defaults; cloud is opt-in via env vars |
| V. Harness-Driven Agent Quality | ✅ PASS | `/harness` required; every agent/tool must have eval coverage before milestone completion |

**Post-design re-check**: All principles pass after Phase 1 design. Package structure and UI contracts are consistent with Principles II, III, and IV. Harness scenario validation in quickstart.md satisfies Principle V.

**Open compliance item (non-blocking)**: Agent framework finalized as Pydantic-AI (see research.md). ADR-005 must be written in `docs/adr/` before M2 implementation begins — this is a workflow prerequisite, not a constitution violation.

## Project Structure

### Documentation (this feature)

```text
specs/001-project-scope/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── ui-flows.md      # Gradio role-scoped UI flow contracts
│   └── agent-tools.md   # Agent tool schemas per role
└── tasks.md             # Phase 2 output (via /speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
StoryWeaver/
├── apps/
│   └── web/                        # Gradio UI entry point
│       ├── app.py                  # App factory, session routing
│       ├── pages/
│       │   ├── landing.py          # Campaign join (join code + display name)
│       │   ├── player/             # Player views
│       │   │   ├── character.py    # Character sheet view/edit
│       │   │   ├── twin_chat.py    # Digital twin conversation
│       │   │   └── history.py      # Story history (read-only for players)
│       │   └── gm/                 # GM views
│       │       ├── characters.py   # All characters overview
│       │       ├── npcs.py         # NPC management + twin chat
│       │       ├── history.py      # Story history (author access)
│       │       ├── world_notes.py  # Private world/lore notes
│       │       └── session_plan.py # GM session planning tool
│       └── components/             # Shared Gradio components
│           ├── banner.py           # AI-unavailable degraded-mode banner
│           └── image_display.py    # Portrait / scene image widget
├── packages/
│   ├── core/                       # Shared domain models, types, errors, config
│   │   ├── models.py               # SQLAlchemy ORM models (all entities)
│   │   ├── schemas.py              # Pydantic schemas for validation
│   │   ├── config.py               # Environment-variable config loader
│   │   └── errors.py               # Domain exceptions
│   ├── rules_earthdawn/            # Earthdawn 4E rules engine (M1)
│   │   ├── character_builder.py    # Guided creation flow logic
│   │   ├── validator.py            # Sanity-check validation (not full legal-build)
│   │   └── data/                   # Distilled mechanics tables (no copyrighted prose)
│   ├── agents/                     # Role agents + digital twins (M2)
│   │   ├── twin/                   # Digital twin base agent (Character and NPC)
│   │   │   ├── agent.py            # Pydantic-AI agent definition
│   │   │   └── tools.py            # Twin tools (recall history, describe trait)
│   │   ├── player_agent/           # Player role agent + tools
│   │   └── gm_agent/               # GM role agent + tools
│   ├── llm/                        # LLM provider abstraction
│   │   ├── interface.py            # LLMProvider ABC
│   │   └── providers/
│   │       ├── ollama.py           # Local default (Ollama OpenAI-compat)
│   │       ├── huggingface.py      # Cloud M5+
│   │       ├── anthropic.py        # Cloud M5+
│   │       └── openai.py           # Cloud M5+
│   ├── imagegen/                   # Image generation abstraction (M3)
│   │   ├── interface.py
│   │   └── providers/
│   │       ├── comfyui.py          # Local default
│   │       └── huggingface.py      # Cloud M5+ (SDXL via HF Inference API)
│   ├── rag/                        # RAG layer (M4.5)
│   │   ├── interface.py            # Retriever ABC
│   │   ├── rules/                  # Rules index (Earthdawn mechanics)
│   │   ├── history/                # Campaign history index
│   │   └── character/              # Character index (twin grounding)
│   ├── storage/                    # DB + sync layer
│   │   ├── interface.py            # StorageBackend ABC
│   │   ├── sqlite/                 # SQLite adapter (local default)
│   │   ├── postgres/               # Postgres adapter (cloud M5+)
│   │   └── sync/                   # Local↔cloud reconciliation (M5+)
│   └── story/                      # Story history / campaign timeline (M4)
│       ├── history.py              # Story event CRUD + query
│       └── session.py              # Session management
├── harness/                        # Agent/tool eval suites
│   ├── scenarios/                  # YAML/JSON scenario fixtures
│   │   ├── twin_dialogue/          # In-character response scenarios
│   │   └── history_recall/         # Story event retrieval scenarios
│   └── scoring/                    # Deterministic scoring logic
│       └── rubrics.py
├── deploy/
│   ├── docker/
│   │   ├── Dockerfile.web          # apps/web image
│   │   └── Dockerfile.ollama       # Ollama sidecar (local)
│   └── compose/
│       ├── docker-compose.local.yml
│       └── docker-compose.cloud.yml
├── docs/
│   └── adr/                        # Architecture Decision Records
│       └── ADR-005-agent-framework.md  # Must exist before M2
├── tests/
│   ├── unit/
│   └── integration/
├── pyproject.toml                  # uv workspace config
├── .env.example
├── README.md
└── CLAUDE.md
```

**Structure Decision**: Monorepo with `apps/web/` as the Gradio entry point and `packages/` for domain logic. Matches the README's proposed layout and directly enforces Constitution Principles II (provider abstraction packages), III (package isolation), and IV (local-first with local provider defaults). Gradio pages are split by role (`player/`, `gm/`) to enforce role-scoped access without privilege checks scattered throughout. `/harness` is a top-level sibling of `tests/` to keep agent eval concerns separate from unit/integration tests.

## Complexity Tracking

> No constitution violations requiring justification. The multi-package monorepo structure is explicitly mandated by the constitution (Principle III) and by the local-first / provider-agnostic design goals (Principles II + IV).