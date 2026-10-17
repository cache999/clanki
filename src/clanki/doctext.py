"""Text of a document's pages, for LLM context and whole-document chunking."""
import re
from pathlib import Path

from pypdf import PdfReader


def clean(s: str) -> str:
    s = "\n".join(line.rstrip() for line in s.splitlines())
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def page_texts(pdf: Path) -> list[str]:
    return [clean(p.extract_text() or "") for p in PdfReader(pdf).pages]


def document_text(pages: list[str], first: int, last: int) -> str:
    """Pages first..last (1-based, inclusive) with [p.N] markers, so cards can cite pages."""
    return "\n\n".join(("[p.%d]\n%s" % (n, pages[n - 1])).rstrip() for n in range(first, last + 1))


def chunk_pages(pages: list[str], max_chars: int = 12000, max_pages: int = 6) -> list[tuple[int, int]]:
    """Consecutive page ranges for whole-document generation. Pages without text (figures,
    title slides) ride along and don't count towards max_pages; a page bigger than max_chars
    is a chunk of its own. A document with no text gives no chunks."""
    chunks: list[tuple[int, int]] = []
    start, size, count = None, 0, 0
    for i, text in enumerate(pages, 1):
        n = len(text.strip())
        if start is None:
            start, size, count = i, n, int(n > 0)
        elif n and count and (count + 1 > max_pages or size + n > max_chars):
            chunks.append((start, i - 1))
            start, size, count = i, n, 1
        else:
            size += n
            count += int(n > 0)
    if start is not None and count:
        chunks.append((start, len(pages)))
    return chunks


def context_window(n_pages: int, page: int, radius: int = 2) -> tuple[int, int]:
    return max(1, page - radius), min(n_pages, page + radius)
