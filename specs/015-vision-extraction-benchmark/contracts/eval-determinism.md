# Contract: Evaluation Determinism (Temperature Passthrough)

**File**: `packages/llm/llm/providers/ollama.py`, `packages/core/core/config.py`
**Status**: New behaviour (feature 015) — implements FR-018

---

## Purpose

Control run-to-run variance during evaluation by decoding greedily (temperature 0) on the LLM steps the benchmark exercises: answer generation (`ask_question` → answer LLM) and the LLM judge (when `JUDGE_PROVIDER=ollama`). Today `OllamaProvider` sends no `temperature`, so Ollama's server default applies and results are non-deterministic.

---

## Settings

Add to `Settings` (`packages/core/core/config.py`), mirrored in `.env.example` and `.env`:

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `knowledge_eval_temperature` | `float` | `0.0` | Decoding temperature for evaluation LLM calls. `0.0` = greedy = deterministic (FR-018). |

Range: `0.0 ≤ value ≤ 2.0`. Out-of-range MUST fail fast at startup with a clear error (mirrors the hybrid-weight validator pattern from 014).

---

## Provider change

`OllamaProvider.generate()` and `generate_structured()` MUST include `temperature` in the `/v1/chat/completions` payload:

```jsonc
{
  "model": "...",
  "messages": [...],
  "stream": false,
  "temperature": 0.0        // NEW — resolved from knowledge_eval_temperature (or per-call override)
  // generate_structured also keeps: "response_format": {"type": "json_object"}
}
```

- The value resolves from `knowledge_eval_temperature` by default; an optional per-call `temperature` argument MAY override it (e.g., product runtime paths that want the prior sampling behaviour can pass their own).
- **Backwards-compatibility note**: defaulting to `0.0` changes decoding for *all* `OllamaProvider.generate` callers, including enrichment during ingestion. This is acceptable and arguably desirable (more reproducible ingestion), but MUST be called out in the PR. If any caller must retain sampling, it passes an explicit `temperature` override.

## Judge path

- When `JUDGE_PROVIDER=ollama`: the judge's provider call resolves temperature from `knowledge_eval_temperature` (0.0).
- When `JUDGE_PROVIDER=claude`: pass `temperature=0` through the existing Anthropic provider call so the cloud judge is equally deterministic.

## Recording

The resulting decoding setting is recorded as `decoding: "greedy"|"sampled"` on both the retrieval record and the eval run (see `benchmark-record-schema.md`).

---

## Guarantees

- Default behaviour after this change is **deterministic greedy decoding** for evaluation, with no repeated passes required (FR-018).
- Residual nondeterminism (local model/runtime nondeterminism even at temp 0) is **not** eliminated; the recommendation MUST note it as a limitation on the confidence of sub-tolerance deltas.
- No provider abstraction is broken: `temperature` is a standard decoding parameter carried inside the existing provider, not a new interface or branch (Constitution II).
