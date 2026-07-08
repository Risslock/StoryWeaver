"""Gold standard benchmark harness for chunking strategy evaluation.

Loads rag_gold_standard.jsonl (118 questions), runs each through ChromaKnowledgeRetriever
with scope="global" and role="gm", computes MRR / nDCG / Recall@10, and appends a
ChunkBenchmarkResult record to benchmark_results.jsonl.

Auto-skips when Ollama is unreachable (same pattern as test_integration.py).
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from rag.knowledge.evaluator import EvalSummary, aggregate_results, evaluate_question
from rag.knowledge.test_questions import TestQuestion, load_test_questions

_log = logging.getLogger(__name__)

GOLD_STANDARD_PATH = os.environ.get(
    "GOLD_STANDARD_PATH",
    str(Path(__file__).parent / "rag_gold_standard.jsonl"),
)
BENCHMARK_RESULTS_PATH = Path(__file__).parent / "benchmark_results.jsonl"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _ollama_reachable() -> bool:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _round4(value: float) -> float:
    return round(value, 4)


def _round_metrics(metrics: dict) -> dict:
    """Round mean_mrr/mean_ndcg/mean_recall_at_k to 4 decimals, matching historical records."""
    rounded = dict(metrics)
    for key in ("mean_mrr", "mean_ndcg", "mean_recall_at_k"):
        if key in rounded and isinstance(rounded[key], float):
            rounded[key] = _round4(rounded[key])
    return rounded


def _resolve_extraction_mode() -> str:
    """Read BENCHMARK_EXTRACTION_MODE (feature 015 run-attribution, FR-011).

    Defaults to "unknown" with a WARNING when unset — the record is still written,
    but the run cannot be attributed to a specific extraction path.
    """
    mode = os.environ.get("BENCHMARK_EXTRACTION_MODE", "").strip()
    if not mode:
        _log.warning(
            "BENCHMARK_EXTRACTION_MODE is not set — recording extraction_mode='unknown'. "
            "Set it to 'docling' or 'vision' to attribute this run to an extraction path."
        )
        return "unknown"
    return mode


def _resolve_decoding(cfg: object) -> str:
    """Return 'greedy' when knowledge_eval_temperature is 0.0, else 'sampled' (FR-018)."""
    return "greedy" if cfg.knowledge_eval_temperature == 0.0 else "sampled"  # type: ignore[attr-defined]


def _display_gold_standard_path(path: str) -> str:
    """Store a repo-relative, forward-slash path for portability across machines/OSes."""
    try:
        relative = Path(path).resolve().relative_to(_REPO_ROOT)
        return relative.as_posix()
    except ValueError:
        return path


def _chunking_params(strategy: str, cfg: object) -> dict[str, object]:
    """Per-strategy params, matching the historical benchmark_results.jsonl convention."""
    if strategy == "agentic":
        return {
            "batch_sections": cfg.knowledge_agentic_batch_sections,
            "max_tokens": cfg.knowledge_max_chunk_tokens,
            "chunking_model": cfg.knowledge_enrich_model,
            "prose_threshold": cfg.knowledge_agentic_prose_threshold,
        }
    if strategy == "semantic":
        return {
            "breakpoint_percentile": cfg.knowledge_semantic_breakpoint_percentile,
            "min_chunk_tokens": cfg.knowledge_semantic_min_chunk_tokens,
        }
    if strategy == "heading":
        return {
            "max_tokens": cfg.knowledge_max_chunk_tokens,
            "overlap_tokens": cfg.knowledge_chunk_overlap_tokens,
        }
    if strategy == "hybrid_chunker":
        return {"tokenizer": cfg.knowledge_embed_model, "max_tokens": cfg.knowledge_max_chunk_tokens}
    return {}


async def run_gold_standard_benchmark(k: int = 10) -> EvalSummary:
    """Run all gold standard questions through the retriever and return aggregate metrics.

    Appends a ChunkBenchmarkResult JSON line to benchmark_results.jsonl.
    Skips via pytest.skip() if Ollama is unreachable.
    """
    if not _ollama_reachable():
        pytest.skip("Ollama not reachable — skipping gold standard benchmark")

    from rag.knowledge.chunker import create_chunker
    from rag.knowledge.retriever import ChromaKnowledgeRetriever

    questions: list[TestQuestion] = load_test_questions(GOLD_STANDARD_PATH)
    retriever = ChromaKnowledgeRetriever()

    eval_results = []
    for test in questions:
        chunks = await retriever.search(
            query=test.question,
            campaign_id="",
            role="gm",
            top_k=k,
        )
        result = evaluate_question(test, chunks, k)
        eval_results.append(result)

    summary = aggregate_results(eval_results)

    print("\n=== Per-Category Results ===")
    print(f"{'Category':<16}{'Questions':<11}{'MRR':<8}{'nDCG':<8}{'Recall@' + str(k)}")
    for cat, metrics in summary.category_scores.items():
        print(
            f"{cat:<16}{metrics.question_count:<11}"
            f"{metrics.mean_mrr:<8.3f}{metrics.mean_ndcg:<8.3f}{metrics.mean_recall_at_k:.3f}"
        )
    print("=== Global ===")
    print(
        f"Total: {summary.total_questions}   "
        f"MRR: {summary.mean_mrr:.3f}   "
        f"nDCG: {summary.mean_ndcg:.3f}   "
        f"Recall@{k}: {summary.mean_recall_at_k:.3f}"
    )

    strategy = create_chunker().strategy_name
    category_scores_serialized = {
        cat: _round_metrics(metrics.model_dump())
        for cat, metrics in summary.category_scores.items()
    }
    from core.config import settings as _cfg

    record = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "chunking": {"strategy": strategy, "params": _chunking_params(strategy, _cfg)},
        "enrich_model": _cfg.knowledge_enrich_model,
        "embed_model": _cfg.knowledge_embed_model,
        "gold_standard_path": _display_gold_standard_path(GOLD_STANDARD_PATH),
        "k": k,
        "total_questions": summary.total_questions,
        "mean_mrr": _round4(summary.mean_mrr),
        "mean_ndcg": _round4(summary.mean_ndcg),
        "mean_recall_at_k": _round4(summary.mean_recall_at_k),
        "notes": "",
        "category_scores": category_scores_serialized,
        "hybrid_search_enabled": _cfg.hybrid_search_enabled,
        "hybrid_search_keyword_weight": _cfg.hybrid_search_keyword_weight,
        "hybrid_search_vector_weight": _cfg.hybrid_search_vector_weight,
        "exact_term_scores": (
            _round_metrics(summary.exact_term_scores.model_dump())
            if summary.exact_term_scores else None
        ),
        "extraction_mode": _resolve_extraction_mode(),
        "decoding": _resolve_decoding(_cfg),
    }
    with open(BENCHMARK_RESULTS_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")

    return summary


def _load_benchmark_records(jsonl_path: str | None = None) -> list[dict]:
    """Load all benchmark records from the JSONL file."""
    path = Path(jsonl_path) if jsonl_path else BENCHMARK_RESULTS_PATH
    if not path.exists():
        return []
    records: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _resolve_selector(records: list[dict], selector: int | str) -> dict:
    """Resolve a selector (integer index or timestamp prefix) to a benchmark record."""
    if not records:
        raise ValueError("No benchmark records found")
    if isinstance(selector, int):
        try:
            return records[selector]
        except IndexError:
            available = [r.get("timestamp", "?") for r in records]
            raise ValueError(
                f"Selector {selector} out of range. Available records: {available}"
            )
    # String: match timestamp prefix
    for record in records:
        if record.get("timestamp", "").startswith(selector):
            return record
    available = [r.get("timestamp", "?") for r in records]
    raise ValueError(
        f"Selector '{selector}' did not match any record timestamp. Available records: {available}"
    )


# Fields that must be identical across the two runs for a valid one-variable
# extraction-path comparison (FR-009 / FR-011). Everything else (metrics,
# timestamp, notes) is expected to differ — that's the point of the comparison.
_HELD_FIXED_FIELDS = (
    "chunking",
    "enrich_model",
    "embed_model",
    "gold_standard_path",
    "k",
    "hybrid_search_enabled",
    "hybrid_search_keyword_weight",
    "hybrid_search_vector_weight",
    "decoding",
)


def assert_comparable_extraction_runs(rec_a: dict, rec_b: dict) -> None:
    """Verify two benchmark records differ ONLY in extraction_mode (FR-009, FR-011, US3 AC1).

    Raises:
        ValueError: naming every held-fixed field that differs between the two records,
            if any mismatch exists.
    """
    mismatches = [
        field
        for field in _HELD_FIXED_FIELDS
        if rec_a.get(field) != rec_b.get(field)
    ]
    if mismatches:
        raise ValueError(
            "Benchmark records are not comparable — the following held-fixed fields "
            f"differ between run A and run B: {mismatches}. "
            f"Run A: { {f: rec_a.get(f) for f in mismatches} }. "
            f"Run B: { {f: rec_b.get(f) for f in mismatches} }. "
            "Only extraction_mode may differ for a valid one-variable comparison."
        )
    if rec_a.get("extraction_mode", "unknown") == rec_b.get("extraction_mode", "unknown"):
        raise ValueError(
            "Benchmark records have the same extraction_mode "
            f"({rec_a.get('extraction_mode', 'unknown')!r}) — nothing to compare."
        )


def compare_benchmark_runs(
    selector_a: int | str,
    selector_b: int | str,
    jsonl_path: str | None = None,
) -> None:
    """Print a per-category diff table comparing two benchmark runs.

    Selectors can be integer indices (negative supported) or timestamp prefix strings.
    """
    records = _load_benchmark_records(jsonl_path)
    rec_a = _resolve_selector(records, selector_a)
    rec_b = _resolve_selector(records, selector_b)

    cats_a: dict = rec_a.get("category_scores", {})
    cats_b: dict = rec_b.get("category_scores", {})
    all_cats = sorted(set(cats_a) | set(cats_b))

    def _fmt(val: object) -> str:
        return f"{val:.4f}" if isinstance(val, float | int) else "N/A"

    def _delta(a: object, b: object) -> str:
        if not isinstance(a, float | int) or not isinstance(b, float | int):
            return "N/A"
        d = b - a
        return f"+{d:.4f}" if d >= 0 else f"{d:.4f}"

    header = (
        f"{'Category':<16} {'MRR-A':>7} {'MRR-B':>7} {'ΔMRR':>8}"
        f" {'nDCG-A':>7} {'nDCG-B':>7} {'ΔnDCG':>8}"
        f" {'Rcl-A':>7} {'Rcl-B':>7} {'ΔRecall':>8}"
    )
    separator = "-" * len(header)

    def _hybrid_desc(rec: dict) -> str:
        enabled = rec.get("hybrid_search_enabled", False)
        kw = rec.get("hybrid_search_keyword_weight", 1.0)
        vw = rec.get("hybrid_search_vector_weight", 1.0)
        return f"hybrid_search_enabled={enabled} keyword_weight={kw} vector_weight={vw}"

    def _attribution(rec: dict) -> str:
        mode = rec.get("extraction_mode", "unknown")
        decoding = rec.get("decoding", "unknown")
        return f"extraction_mode={mode} decoding={decoding}"

    print(f"\nRun A: {rec_a.get('timestamp', '?')}  ({_attribution(rec_a)})")
    print(f"Run B: {rec_b.get('timestamp', '?')}  ({_attribution(rec_b)})")
    print(f"Run A config: {_hybrid_desc(rec_a)}")
    print(f"Run B config: {_hybrid_desc(rec_b)}")
    print(separator)
    print(header)
    print(separator)

    def _row(label: str, a_scores: dict, b_scores: dict) -> None:
        mrr_a = a_scores.get("mean_mrr", "N/A")
        mrr_b = b_scores.get("mean_mrr", "N/A")
        ndcg_a = a_scores.get("mean_ndcg", "N/A")
        ndcg_b = b_scores.get("mean_ndcg", "N/A")
        rcl_a = a_scores.get("mean_recall_at_k", "N/A")
        rcl_b = b_scores.get("mean_recall_at_k", "N/A")
        print(
            f"{label:<16} {_fmt(mrr_a):>7} {_fmt(mrr_b):>7} {_delta(mrr_a, mrr_b):>8}"
            f" {_fmt(ndcg_a):>7} {_fmt(ndcg_b):>7} {_delta(ndcg_a, ndcg_b):>8}"
            f" {_fmt(rcl_a):>7} {_fmt(rcl_b):>7} {_delta(rcl_a, rcl_b):>8}"
        )

    for cat in all_cats:
        _row(cat, cats_a.get(cat, {}), cats_b.get(cat, {}))

    print(separator)
    _row(
        "exact_term",
        rec_a.get("exact_term_scores") or {},
        rec_b.get("exact_term_scores") or {},
    )

    print(separator)
    _row(
        "global",
        {"mean_mrr": rec_a.get("mean_mrr"), "mean_ndcg": rec_a.get("mean_ndcg"), "mean_recall_at_k": rec_a.get("mean_recall_at_k")},
        {"mean_mrr": rec_b.get("mean_mrr"), "mean_ndcg": rec_b.get("mean_ndcg"), "mean_recall_at_k": rec_b.get("mean_recall_at_k")},
    )
    print(separator)


# ── Feature 015 unit tests: run attribution (no Ollama required) ──────────────

class _FakeSettings:
    def __init__(self, knowledge_eval_temperature: float = 0.0) -> None:
        self.knowledge_eval_temperature = knowledge_eval_temperature


def test_resolve_extraction_mode_defaults_to_unknown_with_warning(monkeypatch, caplog) -> None:
    monkeypatch.delenv("BENCHMARK_EXTRACTION_MODE", raising=False)
    with caplog.at_level(logging.WARNING):
        assert _resolve_extraction_mode() == "unknown"
    assert any("BENCHMARK_EXTRACTION_MODE" in rec.message for rec in caplog.records)


def test_resolve_extraction_mode_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("BENCHMARK_EXTRACTION_MODE", "vision")
    assert _resolve_extraction_mode() == "vision"


def test_resolve_decoding_greedy_vs_sampled() -> None:
    assert _resolve_decoding(_FakeSettings(0.0)) == "greedy"
    assert _resolve_decoding(_FakeSettings(0.7)) == "sampled"


def _base_record(**overrides: object) -> dict:
    record: dict = {
        "chunking": {"strategy": "agentic", "params": {}},
        "enrich_model": "llama3.1",
        "embed_model": "nomic-embed-text",
        "gold_standard_path": "harness/knowledge_qa/rag_gold_standard.jsonl",
        "k": 10,
        "hybrid_search_enabled": True,
        "hybrid_search_keyword_weight": 1.0,
        "hybrid_search_vector_weight": 1.0,
        "decoding": "greedy",
        "extraction_mode": "docling",
        "mean_mrr": 0.5,
        "category_scores": {},
    }
    record.update(overrides)
    return record


def test_assert_comparable_extraction_runs_passes_when_only_extraction_mode_differs() -> None:
    rec_a = _base_record(extraction_mode="docling")
    rec_b = _base_record(extraction_mode="vision", mean_mrr=0.6)
    assert_comparable_extraction_runs(rec_a, rec_b)  # must not raise


def test_assert_comparable_extraction_runs_raises_on_held_fixed_mismatch() -> None:
    rec_a = _base_record(extraction_mode="docling", enrich_model="llama3.1")
    rec_b = _base_record(extraction_mode="vision", enrich_model="llama3.2")
    with pytest.raises(ValueError, match="enrich_model"):
        assert_comparable_extraction_runs(rec_a, rec_b)


def test_assert_comparable_extraction_runs_raises_when_same_extraction_mode() -> None:
    rec_a = _base_record(extraction_mode="docling")
    rec_b = _base_record(extraction_mode="docling")
    with pytest.raises(ValueError, match="same extraction_mode"):
        assert_comparable_extraction_runs(rec_a, rec_b)


def test_compare_benchmark_runs_prints_attribution(tmp_path, capsys) -> None:
    jsonl_path = tmp_path / "benchmark_results.jsonl"
    rec_a = _base_record(extraction_mode="docling", timestamp="2026-07-07T00:00:00Z")
    rec_b = _base_record(extraction_mode="vision", timestamp="2026-07-07T01:00:00Z", mean_mrr=0.6)
    with open(jsonl_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rec_a) + "\n")
        fh.write(json.dumps(rec_b) + "\n")

    compare_benchmark_runs(0, 1, jsonl_path=str(jsonl_path))
    out = capsys.readouterr().out
    assert "extraction_mode=docling" in out
    assert "extraction_mode=vision" in out


def test_compare_benchmark_runs_handles_missing_attribution_gracefully(tmp_path, capsys) -> None:
    """Historical records written before feature 015 lack extraction_mode/decoding."""
    jsonl_path = tmp_path / "benchmark_results.jsonl"
    rec_a = _base_record()
    del rec_a["extraction_mode"]
    del rec_a["decoding"]
    rec_b = _base_record(extraction_mode="vision")
    with open(jsonl_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rec_a) + "\n")
        fh.write(json.dumps(rec_b) + "\n")

    compare_benchmark_runs(0, 1, jsonl_path=str(jsonl_path))  # must not raise
    out = capsys.readouterr().out
    assert "extraction_mode=unknown" in out


@pytest.mark.asyncio
async def test_gold_standard_recall_sanity() -> None:
    """Sanity gate: Recall@10 must be ≥ 0.40 (corpus populated, retriever working)."""
    summary = await run_gold_standard_benchmark()
    assert summary.mean_recall_at_k >= 0.40, (
        f"Gold standard Recall@10 = {summary.mean_recall_at_k:.3f} is below 0.40. "
        "Ensure the knowledge base is populated with the Earthdawn rulebook PDF "
        "before running this benchmark."
    )
