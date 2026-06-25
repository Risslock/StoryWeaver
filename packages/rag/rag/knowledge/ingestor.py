"""Ingestor ABC, PdfIngestor (pymupdf4llm), and MarkdownIngestor."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable

from rag.knowledge.chunker import BaseChunker, create_chunker

_log = logging.getLogger(__name__)


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

    def _convert_to_markdown(self, file_path: str) -> list:
        """Return per-page chunks from pymupdf4llm (page_chunks=True).

        Each element is a dict with keys including ``metadata["page_number"]`` (1-indexed)
        and ``text`` (Markdown for that page).
        """
        try:
            import pymupdf4llm  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "pymupdf4llm is required for PDF ingestion. "
                "Add it to packages/rag/pyproject.toml."
            ) from exc

        return pymupdf4llm.to_markdown(file_path, page_chunks=True)

    def _extract_multicolumn_page(self, fitz_page: object) -> str | None:  # type: ignore[type-arg]
        """Detect and reconstruct multi-column layout using fitz block coordinates.

        Returns reordered Markdown text if the page has ≥2 column bands, else None.
        A column gap is detected when ≥2 distinct x0 clusters exist with a gap
        exceeding 20% of the page width.
        """
        try:
            page_dict = fitz_page.get_text("dict")  # type: ignore[union-attr]
            blocks = [b for b in page_dict.get("blocks", []) if b.get("type") == 0]
        except Exception:
            return None

        if len(blocks) < 4:
            return None

        try:
            page_width: float = fitz_page.rect.width  # type: ignore[union-attr]
        except Exception:
            return None

        if page_width <= 0:
            return None

        gap_threshold = page_width * 0.20

        # Collect unique x0 values.
        x0s = sorted({round(b["bbox"][0], 0) for b in blocks})
        if len(x0s) < 2:
            return None

        # Find the largest gap between consecutive x0 values.
        max_gap = max(x0s[i + 1] - x0s[i] for i in range(len(x0s) - 1))
        if max_gap < gap_threshold:
            return None

        # Split blocks into left and right column groups at the gap boundary.
        split_x = next(
            x0s[i] + (x0s[i + 1] - x0s[i]) / 2
            for i in range(len(x0s) - 1)
            if x0s[i + 1] - x0s[i] >= gap_threshold
        )

        left = sorted(
            [b for b in blocks if b["bbox"][0] < split_x],
            key=lambda b: b["bbox"][1],
        )
        right = sorted(
            [b for b in blocks if b["bbox"][0] >= split_x],
            key=lambda b: b["bbox"][1],
        )

        def _block_text(block: dict) -> str:
            return " ".join(
                span["text"]
                for line in block.get("lines", [])
                for span in line.get("spans", [])
            ).strip()

        # Interleave columns: match left and right blocks by overlapping y-ranges.
        ordered: list[str] = []
        ri = 0
        for lb in left:
            ly1 = lb["bbox"][3]
            lt = _block_text(lb)
            if lt:
                ordered.append(lt)
            # Flush right-column blocks that start before the next left block.
            while ri < len(right) and right[ri]["bbox"][1] <= ly1:
                rt = _block_text(right[ri])
                if rt:
                    ordered.append(rt)
                ri += 1
        while ri < len(right):
            rt = _block_text(right[ri])
            if rt:
                ordered.append(rt)
            ri += 1

        return "\n\n".join(ordered) if ordered else None

    def ingest(self, file_path: str) -> list[str]:
        from rag.knowledge.cleaner import CorpusCleaner, PageText
        page_chunks = self._convert_to_markdown(file_path)
        if self._captioner is not None:
            md_text = self._inline_image_captions(file_path, "")
        else:
            md_text = ""
        pages = [
            PageText(page_num=c["metadata"].get("page_number", 1) - 1, text=c["text"])
            for c in page_chunks
        ]
        cleaned = CorpusCleaner().clean_pages(pages, "rulebook")
        text = cleaned.text
        if md_text:
            text += "\n\n" + md_text
        return self._chunker.chunk(text)

    async def ingest_async(
        self,
        file_path: str,
        source_type: str = "rulebook",
        cleaning: bool = True,
    ) -> list[str]:
        """Extract, optionally clean, and chunk a PDF.

        Args:
            file_path: Absolute path to the PDF.
            source_type: Determines which cleaning rules are applied.
            cleaning: When False, skip the cleaner entirely (bypass mode).
        """
        from rag.knowledge.cleaner import CorpusCleaner, PageText

        page_chunks = self._convert_to_markdown(file_path)

        # Optional fitz multi-column pass (rulebook/supplement only).
        multicolumn_count = 0
        if cleaning and source_type in ("rulebook", "supplement"):
            page_chunks, multicolumn_count = self._apply_multicolumn(file_path, page_chunks)

        if cleaning:
            pages = [
                PageText(page_num=c["metadata"].get("page_number", 1) - 1, text=c["text"])
                for c in page_chunks
            ]
            doc_name = file_path.split("/")[-1].split("\\")[-1].rsplit(".", 1)[0]
            cleaned = CorpusCleaner().clean_pages(
                pages, source_type, doc_name=doc_name  # type: ignore[arg-type]
            )
            cleaned.report.multicolumn_pages_reconstructed = multicolumn_count
            text = cleaned.text
        else:
            text = "\n\n".join(c["text"] for c in page_chunks)

        if self._captioner is not None:
            text += self._inline_image_captions(file_path, "")

        return await self._chunker.async_chunk(text)

    def _apply_multicolumn(
        self,
        file_path: str,
        page_chunks: list,
    ) -> tuple[list, int]:
        """Run the fitz multi-column detection pass; replace page text where detected."""
        try:
            import fitz  # type: ignore[import-untyped]
        except ImportError:
            return page_chunks, 0

        try:
            doc = fitz.open(file_path)
        except Exception:
            return page_chunks, 0

        count = 0
        result: list = []
        for chunk in page_chunks:
            page_num = chunk["metadata"].get("page_number", 1) - 1
            try:
                fitz_page = doc[page_num]
                reordered = self._extract_multicolumn_page(fitz_page)
                if reordered is not None:
                    updated = dict(chunk)
                    updated["text"] = reordered
                    result.append(updated)
                    _log.warning(
                        "[corpus-cleaner] Reconstructed multi-column layout (page %d) in '%s'",
                        page_num,
                        file_path.split("/")[-1].split("\\")[-1],
                    )
                    count += 1
                    continue
            except Exception:
                pass
            result.append(chunk)

        doc.close()
        return result, count

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

    async def ingest_async(
        self,
        file_path: str,
        source_type: str = "rulebook",
        cleaning: bool = True,
    ) -> list[str]:
        """Read, optionally clean, and chunk a Markdown file."""
        from rag.knowledge.cleaner import CorpusCleaner
        content = self._read(file_path)
        if cleaning:
            doc_name = file_path.split("/")[-1].split("\\")[-1].rsplit(".", 1)[0]
            cleaned = CorpusCleaner().clean_text(
                content, source_type, doc_name=doc_name  # type: ignore[arg-type]
            )
            content = cleaned.text
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
