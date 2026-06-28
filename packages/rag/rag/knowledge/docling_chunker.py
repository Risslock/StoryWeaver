"""DoclingChunker: thin wrapper around HybridChunker for Docling document objects."""

from __future__ import annotations


class DoclingChunker:
    """Wrap Docling HybridChunker to produce (body_text, headings) pairs.

    Constructs the tokenizer and HybridChunker once; callers should reuse this instance
    across page batches to avoid repeated model loads.
    """

    def __init__(
        self,
        tokenizer_name: str = "nomic-ai/nomic-embed-text-v1.5",
        max_tokens: int = 512,
    ) -> None:
        from transformers import AutoTokenizer  # type: ignore[import-untyped]
        from docling.chunking import HybridChunker  # type: ignore[import-untyped]

        self._tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
        self._chunker = HybridChunker(tokenizer=self._tokenizer, max_tokens=max_tokens)

    def chunk(self, document: object) -> list[tuple[str, list[str]]]:
        """Return (body_text, headings) pairs for all chunks in *document*."""
        return [
            (self._render_text(chunk), list(chunk.meta.headings or []))  # type: ignore[union-attr]
            for chunk in self._chunker.chunk(document)  # type: ignore[arg-type]
        ]

    def _render_text(self, chunk: object) -> str:
        """Render chunk body, using markdown export for table items.

        HybridChunker's chunk.text serializes tables as flat whitespace-separated
        cell values, losing column structure. For table items we call
        export_to_markdown() instead so the |col|col| structure is preserved.
        """
        parts: list[str] = []
        try:
            for item in chunk.meta.doc_items or []:  # type: ignore[union-attr]
                label = str(getattr(item, "label", "")).lower()
                if "table" in label and hasattr(item, "export_to_markdown"):
                    try:
                        md = item.export_to_markdown()
                        if md and md.strip():
                            parts.append(md.strip())
                            continue
                    except Exception:
                        pass
                text = getattr(item, "text", "") or ""
                if text.strip():
                    parts.append(text.strip())
        except Exception:
            return chunk.text  # type: ignore[union-attr]
        return "\n\n".join(parts) if parts else chunk.text  # type: ignore[union-attr]
