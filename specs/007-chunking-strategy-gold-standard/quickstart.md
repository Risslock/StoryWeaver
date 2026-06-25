# Quickstart: Smart Chunking Strategy & Gold Standard Eval

**Feature**: `007-chunking-strategy-gold-standard`

Prerequisites: Ollama running with `nomic-embed-text` pulled and at least one text model.
The Earthdawn rulebook PDF must have been ingested into ChromaDB before the benchmark runs.

---

## 1. Verify gold standard file is in place

```bash
ls harness/knowledge_qa/rag_gold_standard.jsonl
# Expected: file present, 118 lines
wc -l harness/knowledge_qa/rag_gold_standard.jsonl
```

---

## 2. Run the unit tests for the new chunkers

```bash
uv run pytest packages/rag/tests/knowledge/test_chunkers.py -v
```

Expected: all unit tests pass. No Ollama required (unit tests use stub embeddings/LLM).

---

## 3. Record baseline (heading strategy)

Ensure the current knowledge base was ingested with `KNOWLEDGE_CHUNKING_STRATEGY=heading`
(the default):

```bash
KNOWLEDGE_CHUNKING_STRATEGY=heading uv run pytest \
  harness/knowledge_qa/test_gold_standard.py::test_gold_standard_recall_sanity -v -s
```

This appends one record to `harness/knowledge_qa/benchmark_results.jsonl` with
`"strategy": "heading"`. Inspect the file to capture baseline MRR / nDCG / Recall@10
and record them in `research.md`.

---

## 4. Re-ingest with semantic strategy and benchmark

```bash
# Re-ingest (deletes and rebuilds ChromaDB for the document)
KNOWLEDGE_CHUNKING_STRATEGY=semantic python -m scripts.reingest --doc-id <DOC_ID>

# Run benchmark
KNOWLEDGE_CHUNKING_STRATEGY=semantic uv run pytest \
  harness/knowledge_qa/test_gold_standard.py::test_gold_standard_recall_sanity -v -s
```

Inspect `benchmark_results.jsonl` and record the semantic scores in `research.md`.

---

## 5. Re-ingest with agentic strategy and benchmark

```bash
KNOWLEDGE_CHUNKING_STRATEGY=agentic python -m scripts.reingest --doc-id <DOC_ID>

KNOWLEDGE_CHUNKING_STRATEGY=agentic uv run pytest \
  harness/knowledge_qa/test_gold_standard.py::test_gold_standard_recall_sanity -v -s
```

Record agentic scores in `research.md`.

---

## 6. Compare benchmark results

```bash
python -c "
import json; from pathlib import Path
rows = [json.loads(l) for l in Path('harness/knowledge_qa/benchmark_results.jsonl').read_text().splitlines()]
for r in rows:
    print(r['strategy'], r['mean_mrr'], r['mean_ndcg'], r['mean_recall_at_k'])
"
```

Verify that the winning strategy scores ≥ 10% higher MRR and Recall@10 than the baseline.

---

## 7. Set winning strategy as default (post-decision)

Once `research.md` is updated with the recommendation, update `.env` or `docker-compose.yml`:

```
KNOWLEDGE_CHUNKING_STRATEGY=semantic   # or agentic
```

Re-ingest all existing documents. Existing ChromaDB data from the old strategy is
incompatible and must be cleared first.

---

## Switching strategy without re-ingesting

Setting `KNOWLEDGE_CHUNKING_STRATEGY` only affects new ingestion runs. Querying an existing
ChromaDB populated with the heading strategy while the env var says `semantic` will not cause
errors — retrieval is strategy-agnostic. Only ingestion uses the chunker.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `pytest.skip` on gold standard test | Ollama unreachable | Start Ollama: `ollama serve` |
| `ValueError: unknown strategy 'foo'` | Typo in env var | Check `KNOWLEDGE_CHUNKING_STRATEGY` value |
| `ProviderUnavailableError` during agentic ingest | LLM timed out | Increase Ollama timeout or use a smaller model |
| All scores 0.0 | ChromaDB empty or wrong collection | Reingest the document first |
| `benchmark_results.jsonl` missing | First run | File is created on first benchmark run |
