# Research: PDF Extraction Quality & Corpus Cleaning v2

**Phase 0 output for feature 011** | Resolves all NEEDS CLARIFICATION items from Technical Context

---

## 1. Vision LLM Provider Abstraction

**Question**: The existing `LLMProvider` ABC (in `packages/llm/llm/interface.py`) only exposes `generate(prompt, system) -> str` — no image input. How do we add vision extraction without bypassing Constitution II (Provider Abstraction)?

**Decision**: Add a new `VisionLLMProvider` ABC to `packages/llm/llm/interface.py` with a single method:

```python
class VisionLLMProvider(ABC):
    @abstractmethod
    async def extract_page(self, image_bytes: bytes, prompt: str) -> str:
        """Convert a rendered page image to Markdown text."""
```

Implement `OllamaVisionProvider` in `packages/llm/llm/providers/ollama.py` using the Ollama `/api/generate` endpoint with the `images` field (Ollama's multimodal API). The model name is injected at construction time from the `KNOWLEDGE_VISION_MODEL` env var.

**Why not extend OllamaProvider**: Adding `generate_with_image()` directly to `OllamaProvider` would bind vision capability to one provider class, making it impossible to switch vision backends without code changes — a direct Constitution II violation.

**Why not reuse `generate()`**: The existing `generate()` method sends a text-only chat completions payload. Multimodal calls require a different payload structure (`images` field in the `generate` endpoint, not `chat/completions`). Forcing them through the same method would require type-checking or sentinel arguments — worse design than a dedicated ABC.

**Alternatives considered**:
- Calling the Ollama API directly from `VisionPdfIngestor` — rejected (bypasses abstraction, makes provider switching impossible without touching ingestor code).
- A single `OllamaVisionProvider` without an ABC — rejected (violates Constitution II; cannot swap to another local vision provider without changing code).

---

## 2. PDF Page Rendering

**Question**: How do we render PDF pages to images for vision extraction? What DPI/format?

**Decision**: Use `fitz` (PyMuPDF) directly — it is already a transitive dependency via `pymupdf4llm` and is imported inside function bodies in `ingestor.py` (e.g., `import fitz` at lines 234, 287). No new package needed.

**Rendering settings**:
- `matrix = fitz.Matrix(2.0, 2.0)` → 144 DPI (2× the default 72 DPI). This is the sweet spot for vision LLMs: high enough to read small text and table borders; low enough to stay within typical model image-size limits (~1024×1024 px for most Ollama vision models).
- Format: PNG bytes via `pixmap.tobytes("png")`. PNG is lossless, widely supported by vision models, and avoids JPEG compression artifacts on text.

**Alternatives considered**:
- `pdf2image` library → extra dependency, not justified.
- `pymupdf4llm.to_markdown(page_chunks=True)` with page images → pymupdf4llm does not expose rendered images.
- Higher DPI (300): increases image size to 3–4 MB per page, which some models reject; slower network transfer.

---

## 3. Ollama Multimodal API

**Question**: What endpoint and payload format does the Ollama vision API use?

**Decision**: Use the Ollama `POST /api/generate` endpoint (not `/api/chat` or `/v1/chat/completions`) with the following payload:

```json
{
  "model": "minicpm-v",
  "prompt": "...",
  "images": ["<base64-encoded-png>"],
  "stream": false
}
```

The response is a JSON object with a `response` field containing the model's text output.

**Default model**: `minicpm-v` — specifically designed for document understanding, reads table structures and multi-column layouts better than `llava` in benchmarks. Configurable via `KNOWLEDGE_VISION_MODEL` env var.

**Extraction prompt** (system-style instruction in the `prompt` field):
```
Extract all text from this image as structured Markdown.
Preserve headings (# ## ###), bold (**text**), italic (*text*), and table structure (|col|col|).
Output only the Markdown text — no explanations, preamble, or code fences.
```

**Fallback**: If the Ollama call fails or returns empty text, the page is re-extracted via `pymupdf4llm.to_markdown()` (text path). A WARNING is logged with the page number and failure reason.

---

## 4. Encoding Repair Strategy

**Question**: How to fix Windows-1252 → UTF-8 mojibake without adding a new package dependency (`ftfy`, `chardet`)?

**Decision**: A targeted character replacement table in `CorpusCleaner` — no new dependency.

The corpus analysis revealed a finite set of problematic characters, all traceable to Windows-1252 bytes decoded as Latin-1 or UTF-8 replacement chars. The repair table covers the full Windows-1252 "smart punctuation" range:

```python
_WIN1252_MAP = str.maketrans({
    '': '€',  '': '‚',  '': 'ƒ',  '': '„',
    '': '…',  '': '†',  '': '‡',  '': 'ˆ',
    '': '‰',  '': 'Š',  '': '‹',  '': 'Œ',
    '': 'Ž',  '': '‘',  '': '’',  # ' '
    '': '“',  '': '”',  # " "
    '': '•',  '': '–',  '': '—',
    '': '˜',  '': '™',  '': 'š',  '': '›',
    '': 'œ',  '': 'ž',  '': 'Ÿ',
    '�': '',   # strip bare replacement chars that can't be repaired
})
```

Additionally, strip bare `�` replacement characters (U+FFFD) that appear when no valid character mapping exists.

**Why not `ftfy`**: It is a mature library for exactly this purpose, but adding it requires a constitution-level justification (ADR for new dependency). The observed problems are well-defined and finite — a targeted map is simpler, zero-dependency, and fully transparent.

**Why not re-extract with explicit encoding**: `pymupdf4llm` does not expose a charset parameter; encoding artifacts originate in the PDF's internal font encoding, not in pymupdf4llm's output encoding. The text layer is already lost by the time we receive it.

---

## 5. Drop-Cap Detection Algorithm

**Question**: How to detect and repair OCR drop-cap gaps in cleaned Markdown text?

**Decision**: Two-pass heuristic applied to the joined text after dehyphenation:

**Pattern**: A drop-cap gap appears in cleaned Markdown as a paragraph that begins with an isolated single uppercase letter on its own line, immediately followed by a lowercase continuation. In pymupdf4llm output the drop-cap letter lands in its own text span, separated from the body text by a newline.

**Detection regex**:
```python
_DROPCAP_RE = re.compile(r'(?m)^([A-Z])\n([a-z])')
```
When matched: `\1\2` → rejoins the isolated capital with the lowercase start of the next line.

**False-positive guard**: This pattern is restricted to lines containing exactly one uppercase letter followed by `\n` and then a lowercase character. This avoids triggering on:
- Single-letter words at the start of a full sentence ("I walked", "A dwarf") — these have content after the letter on the same line, so `^([A-Z])\n` does not match.
- Roman numeral chapter markers ("I\n\nChapter") — the double newline does not match `\n([a-z])`.

**Alternatives considered**: Scan for paragraphs beginning with a lowercase letter (heuristic that the first letter was dropped) — rejected because too many false positives (continuation paragraphs legitimately start with lowercase after a quote or list item).

---

## 6. Structural Noise Detection — Back-of-Book Pages

**Question**: The current `_strip_toc()` only scans pages up to page ~20 (`frontmatter_threshold + 10`). How to detect and discard A-Z index pages and backer-list pages that appear at the back of the book?

**Decision**: Two new page-level filters in `CorpusCleaner`, applied to ALL pages (not scoped by page number):

**Index page detection**: A page is an index page if >80% of its non-empty lines match either the dot-leader pattern OR the pipe-delimited table-row pattern:
```python
_INDEX_LINE_RE = re.compile(r'^.{1,120}(?:\.{2,}|\|)\s*\d*\s*$')
```
Threshold: if `index_line_count / total_non_empty_lines > 0.80`, discard the page.

**Backer-list page detection**: A page is a backer list if it has more than `BACKER_NAME_THRESHOLD` (default 40) name-like tokens (comma-separated or newline-separated words that are capitalized and ≤3 words each) with fewer than 5 complete sentences (strings ending in `.`, `!`, or `?`). A `re.findall(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2}\b', text)` count provides the name density.

Both filters log at WARNING level with the page number and detection reason before discarding.

**Why not extend `scope_pages`**: The back-of-book index appears after page 480 in ED4_Players_Guide. Extending `scope_pages` to cover the entire document would re-evaluate 500 pages for TOC patterns on every ingestion — wasteful. Content-pattern detection is faster and more precise.

---

## 7. Post-Chunk Quality Gate

**Question**: Where in the pipeline should minimum/maximum chunk size enforcement happen? How does re-split avoid infinite loops?

**Decision**: A `_apply_quality_gate(chunks: list[str], config: IngestionConfig, doc_title: str) -> list[str]` method on `IngestionPipeline`, called once after `_extract()` and before the enrichment loop.

**Algorithm**:
1. Pass 1 — merge stubs: iterate left-to-right; if `len(chunk) < KNOWLEDGE_MIN_CHUNK_CHARS`, append it to the previous chunk (or the next chunk if it is the first). Single-chunk documents are returned as-is.
2. Pass 2 — split giants: iterate; if `len(chunk) > KNOWLEDGE_MAX_CHUNK_CHARS`, call `create_chunker().chunk(chunk)` to re-split. The returned sub-chunks replace the original. Re-split sub-chunks are NOT re-evaluated by the giant-split pass (loop runs on the original list, not recursively) — this prevents infinite loops when the chunker cannot split below the threshold due to content structure.
3. Pass 3 — merge any new stubs produced by splitting: repeat Pass 1 once more.

**Defaults**:
- `KNOWLEDGE_MIN_CHUNK_CHARS = 150` — env var, falls back to `150`
- `KNOWLEDGE_MAX_CHUNK_CHARS = 15000` — env var, falls back to `15000`

These are character counts (not token counts) for simplicity. The existing `KNOWLEDGE_MAX_CHUNK_TOKENS` continues to govern the chunker's internal splitting; these are post-chunking safety nets.

---

## 8. Benchmark Comparison Function

**Question**: How should the comparison tool select records from `benchmark_results.jsonl`?

**Decision**: A `compare_benchmark_runs(selector_a, selector_b, jsonl_path)` function in `harness/knowledge_qa/test_gold_standard.py`. Selectors are integers (index into the list of records, supporting negative indexing: `-1` = last, `-2` = second-to-last) or ISO timestamp strings (matched against the `timestamp` field). The function reads the entire JSONL file, resolves both selectors, and prints the diff table to stdout.

No new file needed — the function is a sibling of `run_gold_standard_benchmark()` in the same module.
