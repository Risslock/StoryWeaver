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

    async def extract_with_context(
        self,
        file_path: str,
        config: object,
    ) -> tuple[str, list[str]]:
        """Return (full_cleaned_markdown_text, chunks).

        Subclasses override this to expose the full text for breadcrumb extraction.
        """
        raise NotImplementedError


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

        Detection strategy:
        1. Cluster block x0 values within a 25 pt tolerance (cells in the same column
           land at slightly different x0; clustering merges them into one band).
        2. Find the largest gap *between clusters* (right edge of one → left edge of next).
        3. Trigger when that inter-cluster gap exceeds 20% of page width AND both sides
           of the split have ≥3 blocks (prevents a lone page number or thin sidebar
           from being treated as a column).
        """
        try:
            page_dict = fitz_page.get_text("dict")  # type: ignore[union-attr]
            blocks = [b for b in page_dict.get("blocks", []) if b.get("type") == 0]
        except Exception:
            return None

        if len(blocks) < 6:  # need at least 3 per column
            return None

        try:
            page_width: float = fitz_page.rect.width  # type: ignore[union-attr]
        except Exception:
            return None

        if page_width <= 0:
            return None

        gap_threshold = page_width * 0.20

        # For gap analysis, exclude spanning blocks (wider than gap_threshold).
        # Centered table titles bridge the inter-column space and mask genuine gaps.
        # All blocks are still used for the final left/right split and text output.
        analysis_blocks = [b for b in blocks if (b["bbox"][2] - b["bbox"][0]) < gap_threshold]
        if len(analysis_blocks) < 6:
            return None

        # Cluster x0 values: blocks within 25 pts are in the same column band.
        cluster_tol = 25.0
        sorted_x0s = sorted(b["bbox"][0] for b in analysis_blocks)
        clusters: list[tuple[float, float]] = []  # (min_x0, max_x0) per cluster
        for x in sorted_x0s:
            if clusters and x - clusters[-1][1] <= cluster_tol:
                clusters[-1] = (clusters[-1][0], x)
            else:
                clusters.append((x, x))

        if len(clusters) < 2:
            return None

        # Find largest gap between cluster right-edge and next cluster left-edge.
        best_gap = 0.0
        best_split = 0.0
        for i in range(len(clusters) - 1):
            gap = clusters[i + 1][0] - clusters[i][1]
            if gap > best_gap:
                best_gap = gap
                best_split = clusters[i][1] + gap / 2

        if best_gap < gap_threshold:
            return None

        split_x = best_split

        # Split ALL blocks (including wide spanning ones) at the detected boundary.
        left = sorted(
            [b for b in blocks if b["bbox"][0] < split_x],
            key=lambda b: b["bbox"][1],
        )
        right = sorted(
            [b for b in blocks if b["bbox"][0] >= split_x],
            key=lambda b: b["bbox"][1],
        )

        # Both sides must have substantial content; a lone page number is not a column.
        if len(left) < 3 or len(right) < 3:
            return None

        def _block_text(block: dict) -> str:
            return " ".join(
                span["text"]
                for line in block.get("lines", [])
                for span in line.get("spans", [])
            ).strip()

        # Choose reconstruction order based on y-extent overlap.
        # When both columns share nearly the same y-range (parallel lookup table like
        # Step/Action Dice), read left column completely then right (column-first).
        # When y-ranges are staggered (magazine two-column prose), interleave by y.
        try:
            page_height: float = fitz_page.rect.height  # type: ignore[union-attr]
        except Exception:
            page_height = 792.0

        right_min_y = right[0]["bbox"][1]
        # Find the left blocks that overlap with the right column's y-range.
        left_in_range = [b for b in left if b["bbox"][3] >= right_min_y]
        left_in_range_min_y = left_in_range[0]["bbox"][1] if left_in_range else right_min_y

        y_skew = abs(left_in_range_min_y - right_min_y)
        parallel = y_skew < page_height * 0.10  # both columns start at similar y

        ordered: list[str] = []
        if parallel:
            # Parallel lookup table: emit left column in full, then right column.
            ordered = [t for b in left if (t := _block_text(b))]
            ordered += [t for b in right if (t := _block_text(b))]
        else:
            # Magazine-style: interleave left and right blocks by y-coordinate.
            ri = 0
            for lb in left:
                ly1 = lb["bbox"][3]
                lt = _block_text(lb)
                if lt:
                    ordered.append(lt)
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

        # Open fitz once so multicolumn detection and pymupdf4llm share the parsed document,
        # avoiding a second full PDF parse for rulebook/supplement source types.
        multicolumn_count = 0
        fitz_doc = None
        if cleaning and source_type in ("rulebook", "supplement"):
            try:
                import fitz  # type: ignore[import-untyped]
                fitz_doc = fitz.open(file_path)
            except Exception:
                fitz_doc = None

        if fitz_doc is not None:
            try:
                import pymupdf4llm  # type: ignore[import-untyped]
                page_chunks = pymupdf4llm.to_markdown(fitz_doc, page_chunks=True)
            except Exception:
                page_chunks = self._convert_to_markdown(file_path)
            page_chunks, multicolumn_count = self._apply_multicolumn_from_doc(fitz_doc, page_chunks)
        else:
            page_chunks = self._convert_to_markdown(file_path)

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
            if fitz_doc is not None:
                text += self._inline_image_captions_from_doc(fitz_doc, "")
            else:
                text += self._inline_image_captions(file_path, "")

        if fitz_doc is not None:
            fitz_doc.close()

        return await self._chunker.async_chunk(text)

    async def extract_with_context(
        self,
        file_path: str,
        config: object,
    ) -> tuple[str, list[str]]:
        """Return (full_cleaned_markdown_text, chunks) for breadcrumb extraction."""
        from rag.knowledge.interface import IngestionConfig
        cfg: IngestionConfig = config  # type: ignore[assignment]
        from rag.knowledge.cleaner import CorpusCleaner, PageText

        multicolumn_count = 0
        fitz_doc = None
        if cfg.cleaning and cfg.source_type in ("rulebook", "supplement"):
            try:
                import fitz  # type: ignore[import-untyped]
                fitz_doc = fitz.open(file_path)
            except Exception:
                fitz_doc = None

        if fitz_doc is not None:
            try:
                import pymupdf4llm  # type: ignore[import-untyped]
                page_chunks = pymupdf4llm.to_markdown(fitz_doc, page_chunks=True)
            except Exception:
                page_chunks = self._convert_to_markdown(file_path)
            page_chunks, multicolumn_count = self._apply_multicolumn_from_doc(fitz_doc, page_chunks)
        else:
            page_chunks = self._convert_to_markdown(file_path)

        if cfg.cleaning:
            pages = [
                PageText(page_num=c["metadata"].get("page_number", 1) - 1, text=c["text"])
                for c in page_chunks
            ]
            doc_name = file_path.split("/")[-1].split("\\")[-1].rsplit(".", 1)[0]
            cleaned = CorpusCleaner().clean_pages(
                pages, cfg.source_type, doc_name=doc_name  # type: ignore[arg-type]
            )
            cleaned.report.multicolumn_pages_reconstructed = multicolumn_count
            full_text = cleaned.text
        else:
            full_text = "\n\n".join(c["text"] for c in page_chunks)

        if fitz_doc is not None:
            fitz_doc.close()

        chunks = await self._chunker.async_chunk(full_text)
        return full_text, chunks

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

        result, count = self._apply_multicolumn_from_doc(doc, page_chunks)
        doc.close()
        return result, count

    def _apply_multicolumn_from_doc(
        self,
        doc: object,
        page_chunks: list,
    ) -> tuple[list, int]:
        """Run multi-column detection on an already-open fitz document."""
        count = 0
        result: list = []
        for chunk in page_chunks:
            page_num = chunk["metadata"].get("page_number", 1) - 1
            try:
                fitz_page = doc[page_num]  # type: ignore[index]
                reordered = self._extract_multicolumn_page(fitz_page)
                if reordered is not None:
                    updated = dict(chunk)
                    updated["text"] = reordered
                    result.append(updated)
                    _log.warning(
                        "[corpus-cleaner] Reconstructed multi-column layout (page %d)",
                        page_num,
                    )
                    count += 1
                    continue
            except Exception:
                pass
            result.append(chunk)
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

    def _inline_image_captions_from_doc(self, doc: object, md_text: str) -> str:
        """Same as _inline_image_captions but uses an already-open fitz document."""
        caption_lines: list[str] = []
        try:
            for page_num, page in enumerate(doc, 1):  # type: ignore[call-overload]
                image_list = page.get_images(full=True)
                for img_idx, img_info in enumerate(image_list, 1):
                    try:
                        xref = img_info[0]
                        base_image = doc.extract_image(xref)  # type: ignore[union-attr]
                        img_bytes = base_image["image"]
                        caption = self._captioner(img_bytes)  # type: ignore[misc]
                    except Exception:
                        caption = f"[Figure: page {page_num}, image {img_idx}]"
                    caption_lines.append(caption)
        except Exception:
            pass

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

    async def extract_with_context(
        self,
        file_path: str,
        config: object,
    ) -> tuple[str, list[str]]:
        """Return (full_markdown_text, chunks) for breadcrumb extraction."""
        from rag.knowledge.cleaner import CorpusCleaner
        from rag.knowledge.interface import IngestionConfig
        cfg: IngestionConfig = config  # type: ignore[assignment]
        content = self._read(file_path)
        if cfg.cleaning:
            doc_name = file_path.split("/")[-1].split("\\")[-1].rsplit(".", 1)[0]
            cleaned = CorpusCleaner().clean_text(
                content, cfg.source_type, doc_name=doc_name  # type: ignore[arg-type]
            )
            content = cleaned.text
        chunks = await self._chunker.async_chunk(content)
        return content, chunks

    def _read(self, file_path: str) -> str:
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except OSError as exc:
            raise OSError(f"Cannot read Markdown file '{file_path}': {exc}") from exc

        if not content.strip():
            raise ValueError(f"Markdown file '{file_path}' is empty or contains only whitespace.")

        return content
