# ADR-005: Agent Framework Selection

**Date**: 2026-06-18
**Status**: Accepted
**Deciders**: StoryWeaver project (portfolio)

---

## Context

StoryWeaver requires an agent framework to power digital twins (one agent instance per
Character or NPC entity) and role agents (Player Agent, GM Agent). The framework must:

- Work natively with Ollama's OpenAI-compatible REST API (local-first, no cloud required)
- Support typed tool definitions with input/output schemas (Constitution Principle V —
  evals must be able to assert tool call correctness)
- Allow one `Agent` instance per entity with its own system prompt and context window
- Remain model-agnostic so switching LLM providers requires only a config change
  (Constitution Principle II)
- Stay lightweight — avoid pulling in large ecosystems unnecessarily

## Decision

**Selected: [Pydantic-AI](https://ai.pydantic.dev/)**

Pydantic-AI is used as the agent framework for all agents in StoryWeaver.

## Rationale

| Criterion | Pydantic-AI | LangGraph | Lightweight Custom |
|-----------|-------------|-----------|-------------------|
| Type safety | Full Pydantic v2 | Partial | Self-imposed |
| Model-agnostic | Yes (any OpenAI-compat) | Yes (via adapters) | Yes |
| Ollama support | Native (OpenAI-compat API) | Yes | Yes |
| Tool definition | Decorator-based, typed | More verbose | Manual |
| Multi-agent / handoffs | Agent handoff primitives | State machine graphs | Manual |
| Digital twin pattern fit | One `Agent` instance per entity | Node-per-entity awkward | Yes |
| Dependency weight | Minimal (pydantic v2 + httpx) | Heavy (langgraph + langchain) | Zero |
| Portfolio clarity | Shows typed agent design | Hides patterns in graph | Explicit, but verbose |

### Why Pydantic-AI

1. **Type-safe tool schemas**: Pydantic-AI's decorator-based tools with `RunContext`
   produce fully typed `InputModel` / `OutputModel` pairs. This is a prerequisite for
   deterministic harness scoring (Constitution Principle V) — the harness can assert
   exact tool call arguments and validate return types structurally.

2. **Per-entity agent instances**: The `Agent(model, system_prompt=...)` constructor
   creates lightweight, self-contained agents. Instantiating one per Character or NPC
   is natural and maps directly to the digital twin concept. LangGraph's graph-per-entity
   pattern is awkward and adds unnecessary statefulness.

3. **Model-agnostic via OpenAI-compat**: Pydantic-AI's `OpenAIModel` works with any
   OpenAI-compatible endpoint, including Ollama (`http://localhost:11434/v1`). Switching
   to Anthropic or OpenAI cloud requires only a config/env-var change — no code changes.

4. **Lightweight footprint**: Runtime dependencies are `pydantic>=2` and `httpx`. No
   LangChain ecosystem, no graph libraries, no extra abstraction layers.

5. **Portfolio visibility**: Pydantic-AI's structured agent definitions make the design
   intent legible in the code. A reviewer can read `@agent.tool` definitions and
   understand the agent's capabilities without deciphering a graph DSL.

## Alternatives Considered

### LangGraph

- Rejected: The state-machine graph abstraction adds meaningful complexity without
  matching benefit for StoryWeaver's use case. Graphs are well-suited for workflows
  with conditional branching and human-in-the-loop, but digital twins are simple
  request-response entities. LangGraph also pulls in the full LangChain ecosystem
  (~50+ transitive dependencies), conflicting with the local-first / lightweight goal.

### Lightweight Custom (no framework)

- Rejected: Writing typed tool schemas, model routing, and context management from
  scratch is well-understood work, but the result would be functionally equivalent to
  Pydantic-AI with more boilerplate. Pydantic-AI exposes enough internals to demonstrate
  genuine understanding of agent design while avoiding reinventing the plumbing.

## Consequences

- All agents live in `packages/agents/` and import from `pydantic_ai`.
- `packages/llm/interface.py` defines a `LLMProvider` ABC that wraps the Pydantic-AI
  model backend, keeping the `agents` package from importing provider-specific SDKs
  directly (Constitution Principle II).
- Harness evals in `harness/scenarios/` can assert tool input/output schemas
  structurally because Pydantic-AI produces Pydantic models for all tool I/O.
- If Pydantic-AI's API changes materially, the impact is isolated to `packages/agents/`.
  The `LLMProvider` ABC means the rest of the codebase is insulated.

## Compliance

- Constitution Principle II (Provider Abstraction): ✅ Pydantic-AI model backend is
  wrapped behind `packages/llm/interface.py`; no agent imports provider SDKs directly.
- Constitution Principle V (Harness-Driven Quality): ✅ Typed tool I/O enables
  deterministic assertion in harness scenarios; every agent must have eval coverage
  before its milestone is marked complete.
