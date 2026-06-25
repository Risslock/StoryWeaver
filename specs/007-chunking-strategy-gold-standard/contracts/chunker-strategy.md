# Contract: Chunker Strategy Interface

**Feature**: `007-chunking-strategy-gold-standard`
**Module**: `packages/rag/rag/knowledge/chunker.py`

---

## BaseChunker ABC

```python
class BaseChunker(ABC):

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Return 'heading', 'semantic', or 'agentic'."""

    @abstractmethod
    def chunk(self, text: str) -> list[str]:
        """Split Markdown text into non-empty, semantically coherent chunks.

        Invariants (all implementations MUST honour):
        - Returns [] for empty or whitespace-only input.
        - No returned string is empty or whitespace-only.
        - A Markdown table and its immediately preceding heading stay in the same chunk
          unless the table alone exceeds the max_tokens budget.
        - No chunk exceeds max_tokens (approximate, 4 chars ≈ 1 token).
        """

    async def async_chunk(self, text: str) -> list[str]:
        """Async variant. Default: runs chunk() in a thread pool executor.

        AgenticChunker overrides this to call the LLM without blocking.
        All other callers (IngestionPipeline) use this method exclusively.
        """
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(None, self.chunk, text)
```

---

## Factory Function

```python
def create_chunker(
    embed_fn: EmbedFunction | None = None,
    llm_provider: LLMProvider | None = None,
) -> BaseChunker:
    """Read KNOWLEDGE_CHUNKING_STRATEGY and return the correct BaseChunker.

    KNOWLEDGE_CHUNKING_STRATEGY values:
      'heading'  → HeadingChunker (default, current behaviour)
      'semantic' → SemanticChunker(embed_fn=embed_fn or get_embed_fn())
      'agentic'  → AgenticChunker(llm_provider=llm_provider or OllamaProvider(...))

    Raises ValueError for unrecognised strategy names.
    """
```

---

## HeadingChunker

```python
class HeadingChunker(BaseChunker):
    """Current MarkdownChunker logic, renamed.

    Public interface identical to MarkdownChunker.chunk(). All existing callers
    that instantiate MarkdownChunker directly MUST be updated to use
    create_chunker() or HeadingChunker() instead.

    MarkdownChunker is kept as a deprecated alias (emits DeprecationWarning) for
    one release cycle, then removed.
    """
    strategy_name = "heading"
```

---

## SemanticChunker

```python
class SemanticChunker(BaseChunker):
    """Splits at embedding-similarity breakpoints between adjacent sentences.

    Constructor args:
        embed_fn:  EmbedFunction — must implement embed(texts: list[str]) -> list[list[float]]
        max_tokens: int (default: KNOWLEDGE_MAX_CHUNK_TOKENS env var or 800)
        breakpoint_percentile: int (default: KNOWLEDGE_SEMANTIC_BREAKPOINT_PERCENTILE or 95)
        min_chunk_tokens: int (default: KNOWLEDGE_SEMANTIC_MIN_CHUNK_TOKENS or 50)

    chunk() is synchronous; all embedding calls are batched in one embed_fn.embed() call.
    """
    strategy_name = "semantic"
```

---

## AgenticChunker

```python
class AgenticChunker(BaseChunker):
    """Splits heading sections using LLM-identified proposition boundaries.

    Constructor args:
        llm_provider: LLMProvider — must support structured JSON output
        max_tokens: int (default: KNOWLEDGE_MAX_CHUNK_TOKENS env var or 800)
        batch_sections: int (default: KNOWLEDGE_AGENTIC_BATCH_SECTIONS or 1)

    chunk() raises NotImplementedError — always call async_chunk().
    async_chunk() overrides BaseChunker default; calls llm_provider directly.

    LLM prompt contract:
        System: "You are a document chunker for a tabletop RPG knowledge base."
        User: "Split the following section into self-contained propositions. Return a JSON
               object: {\"splits\": [<sentence_index_int>, ...]} where each index starts a
               new chunk. Do not include index 0 (the start is always a new chunk)."
        Expected response: {"splits": [3, 7, 11]}  (sentence indices that begin new chunks)

    On LLM failure or unparseable response: raises ProviderUnavailableError (caught by
    IngestionPipeline and surfaced as UI error per Principle VII).
    """
    strategy_name = "agentic"
```

---

## Ingestor Injection

Both ingestors accept `BaseChunker` instead of `MarkdownChunker`:

```python
class PdfIngestor(Ingestor):
    def __init__(
        self,
        image_captioner: Callable[[bytes], str] | None = None,
        chunker: BaseChunker | None = None,
    ) -> None:
        self._chunker = chunker or create_chunker()

    async def ingest_async(self, file_path: str) -> list[str]:
        """Async variant used by IngestionPipeline."""
        md_text = self._convert_to_markdown(file_path)
        return await self._chunker.async_chunk(md_text)

    def ingest(self, file_path: str) -> list[str]:
        """Sync variant kept for backward compatibility in tests."""
        md_text = self._convert_to_markdown(file_path)
        return self._chunker.chunk(md_text)

class MarkdownIngestor(Ingestor):
    def __init__(self, chunker: BaseChunker | None = None) -> None:
        self._chunker = chunker or create_chunker()
    # ingest() and ingest_async() follow the same pattern
```

---

## IngestionPipeline Change

`_extract_chunks` becomes async:

```python
async def _extract_chunks(self, file_path: str, format: str) -> list[str]:
    if format == "pdf":
        from rag.knowledge.ingestor import PdfIngestor
        return await PdfIngestor().ingest_async(file_path)
    from rag.knowledge.ingestor import MarkdownIngestor
    return await MarkdownIngestor().ingest_async(file_path)
```

Callers inside `run()` change from `chunks = self._extract_chunks(...)` to
`chunks = await self._extract_chunks(...)`.

---

## Gold Standard Harness Contract

```python
# harness/knowledge_qa/test_gold_standard.py

GOLD_STANDARD_PATH = os.environ.get(
    "GOLD_STANDARD_PATH",
    str(Path(__file__).parent / "rag_gold_standard.jsonl"),
)
BENCHMARK_RESULTS_PATH = Path(__file__).parent / "benchmark_results.jsonl"

def run_gold_standard_benchmark(k: int = 10) -> EvalSummary:
    """Load gold standard, run retrieval, compute metrics, append to benchmark_results.jsonl.

    Skips (pytest.skip) if Ollama is unreachable.
    Returns EvalSummary for programmatic inspection.
    """

def test_gold_standard_recall_sanity() -> None:
    """Assert mean Recall@10 >= 0.40 against the active knowledge base.

    This is a sanity gate (corpus is populated and chunking is working), not a
    performance comparison gate. The >=10% improvement claim is verified by
    inspecting benchmark_results.jsonl across strategy runs.
    """
```
