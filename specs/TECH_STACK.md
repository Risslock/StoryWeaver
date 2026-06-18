# Tech Stack

**Status:** active  
**Last updated:** 2026-06-18

---

## Language

| Choice | Rationale |
|--------|-----------|
| **Python 3.11+** | Dominant AI/ML ecosystem; best library coverage for LLMs, vector stores, and image gen |
| **Rust / C++ (optional)** | Only where it earns its place — heavy rules math, image pipelines. Exposed via Python bindings under `packages/<name>/native/`. Never required to build by default. |

---

## UI

| Choice | Rationale |
|--------|-----------|
| **Gradio** | Browser-friendly, minimal front-end effort; well-suited to AI demos and internal tooling. No separate JS build step. |
| **FastAPI (optional)** | Added only if/when a separate backend API is needed (e.g. multi-client or cloud deployment). Not in scope for M1–M3. |

---

## LLM

| Provider | When used | Notes |
|----------|-----------|-------|
| **Ollama / llama.cpp** | Local development (default) | Zero cost, full privacy, requires GPU or Apple Silicon for reasonable speed |
| **HuggingFace Inference API** | Cloud, free tier | No local GPU needed; rate-limited (~10–30 req/min); best for solo/small-group use |
| **Anthropic** | Cloud, M5+ | High quality; paid |
| **OpenAI API** | Cloud, M5+ | As a simple interface to state-of-the-art AI models (OLLAMA, OPENAI, others)|

All providers sit behind a single abstraction layer (`packages/llm/`). Switching is config-only (`LLM_PROVIDER=...`).

### Recommended models (HuggingFace free tier)

| Use case | Model |
|----------|-------|
| Digital twins / dialogue | `mistralai/Mistral-7B-Instruct-v0.3` |
| GM narration | `meta-llama/Llama-3.1-8B-Instruct` |
| Long-context recap | `Qwen/Qwen2.5-7B-Instruct` |

---

## Embeddings

| Provider | Model | When used |
|----------|-------|-----------|
| **Ollama** | `nomic-embed-text` | Local development |
| **HuggingFace** | `BAAI/bge-base-en-v1.5` | Cloud, free serverless endpoint |

---

## Vector Store

| Choice | When used | Notes |
|--------|-----------|-------|
| **ChromaDB** | Local | File-backed, zero-config |
| **pgvector** | Cloud | Extension on the same Postgres instance as relational data |

Switched via `VECTOR_STORE=chroma` or `VECTOR_STORE=pgvector`.

---

## Image Generation

| Provider | Backend | When used |
|----------|---------|-----------|
| **Local** | Stable Diffusion / ComfyUI | Development; full privacy |
| **Cloud** | HUgging Face API | M5+; decided in ADR before adoption |

---

## Storage

| Scope | Technology | Notes |
|-------|-----------|-------|
| Local DB | **SQLite** | Default; file-backed; no setup |
| Cloud DB | **Postgres** | M5+; also hosts pgvector |
| Sync | Custom sync layer | `packages/storage/` — reconciles local↔cloud |

---

## Agent Framework

**Status: OPEN DECISION — see [ADR-005](adr/ADR-005-agent-framework.md)**

Candidates: Pydantic-AI, LangGraph, lightweight custom. Must be decided and recorded as an ADR before M2 implementation begins.

---

## Dependency Management

| Choice | Rationale |
|--------|-----------|
| **uv** (recommended) | Fast, monorepo-friendly, modern |

---

## Containers

| Tool | Purpose |
|------|---------|
| **Docker** | Package the app and services |
| **Docker Compose** | Orchestrate local and cloud environments (`deploy/compose/`) |

---

## Testing & Evaluation

| Tool | Purpose |
|------|---------|
| **pytest** | Unit and integration tests |
| **harness** (`/harness`) | Eval suites for agent/tool behaviour — deterministic scoring over non-deterministic outputs |