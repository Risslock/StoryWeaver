"""Ingestor ABC, PdfIngestor (pymupdf4llm), and MarkdownIngestor."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from rag.knowledge.chunker import BaseChunker, create_chunker


class Ingestor(ABC):
    """Convert a source file into a list of raw text chunks ready for enrichment."""

    @abstractmethod
    def ingest(self, file_path: str) -> list[str]:
        """Return text chunks extracted from the file at file_path."""


class PdfIngestor(Ingestor):
    """Convert a PDF to Markdown via pymupdf4llm then chunk the result.

    Args:
        image_captioner: Optional callable that accepts image bytes and returns
            a short text description. When None, emits a visible placeholder
            ``[Figure: page {p}, image {n}]`` instead of silently skipping images.
    """

    def __init__(
        self,
        image_captioner: Callable[[bytes], str] | None = None,
        chunker: BaseChunker | None = None,
    ) -> None:
        self._captioner = image_captioner
        self._chunker = chunker or create_chunker()

    def _convert_to_markdown(self, file_path: str) -> str:
        try:
            import pymupdf4llm  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "pymupdf4llm is required for PDF ingestion. "
                "Add it to packages/rag/pyproject.toml."
            ) from exc

        md_text = pymupdf4llm.to_markdown(file_path)

        if self._captioner is not None:
            md_text = self._inline_image_captions(file_path, md_text)

        return md_text

    def ingest(self, file_path: str) -> list[str]:
        return self._chunker.chunk(self._convert_to_markdown(file_path))

    async def ingest_async(self, file_path: str) -> list[str]:
        return await self._chunker.async_chunk(self._convert_to_markdown(file_path))

    def _inline_image_captions(self, file_path: str, md_text: str) -> str:
        """Insert image captions as Markdown paragraphs.

        pymupdf4llm does not expose per-page image positions in the Markdown
        output, so captions are appended as a dedicated section at the end.
        This keeps the searchable text coverage complete without filesystem I/O.
        """
        try:
            import fitz  # type: ignore[import-untyped]
        except ImportError:
            return md_text

        doc = fitz.open(file_path)
        caption_lines: list[str] = []
        for page_num, page in enumerate(doc, 1):
            image_list = page.get_images(full=True)
            for img_idx, img_info in enumerate(image_list, 1):
                try:
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    img_bytes = base_image["image"]
                    caption = self._captioner(img_bytes)  # type: ignore[misc]
                except Exception:
                    caption = f"[Figure: page {page_num}, image {img_idx}]"
                caption_lines.append(caption)

        doc.close()

        if caption_lines:
            md_text += "\n\n## Image Descriptions\n\n" + "\n\n".join(caption_lines)

        return md_text


class MarkdownIngestor(Ingestor):
    """Read a Markdown file directly and chunk it.

    No PDF conversion step — chunks go straight into the RAG pipeline.
    """

    def __init__(self, chunker: BaseChunker | None = None) -> None:
        self._chunker = chunker or create_chunker()

    def ingest(self, file_path: str) -> list[str]:
        content = self._read(file_path)
        return self._chunker.chunk(content)

    async def ingest_async(self, file_path: str) -> list[str]:
        content = self._read(file_path)
        return await self._chunker.async_chunk(content)

    def _read(self, file_path: str) -> str:
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except OSError as exc:
            raise OSError(f"Cannot read Markdown file '{file_path}': {exc}") from exc

        if not content.strip():
            raise ValueError(f"Markdown file '{file_path}' is empty or contains only whitespace.")

        return content
