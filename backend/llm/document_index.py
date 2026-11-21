"""Chunk and index approved, finalized Markdown pages."""

from __future__ import annotations

from hashlib import sha256
import re
from pathlib import Path
from typing import Any, Sequence

from backend.storage.repository import SQLiteRepository
from .embedding_client import OllamaEmbeddingClient
from .vector_store import LocalPassageIndex, Passage


_DEFAULT_MAX_CHARS = 1200
_DEFAULT_OVERLAP = 120


def split_markdown_pages(pages: Sequence[str], max_chars: int = _DEFAULT_MAX_CHARS,
                         overlap: int = _DEFAULT_OVERLAP) -> list[Passage]:
    if max_chars < 1 or overlap < 0 or overlap >= max_chars:
        raise ValueError("Chunk size must be positive and overlap smaller than chunk size")
    passages: list[Passage] = []
    for page_number, page in enumerate(pages, start=1):
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", page) if part.strip()]
        for paragraph in paragraphs:
            sentences = re.split(r"(?<=[.!?;:])\s+", paragraph)
            current = ""
            for sentence in sentences:
                if len(sentence) > max_chars:
                    if current:
                        passages.append(_passage(page_number, len(passages), current))
                        current = ""
                    start = 0
                    while start < len(sentence):
                        piece = sentence[start:start + max_chars]
                        passages.append(_passage(page_number, len(passages), piece))
                        if start + max_chars >= len(sentence):
                            break
                        start += max_chars - overlap
                elif current and len(current) + len(sentence) + 1 > max_chars:
                    passages.append(_passage(page_number, len(passages), current))
                    current = sentence
                else:
                    current = f"{current} {sentence}".strip()
            if current:
                passages.append(_passage(page_number, len(passages), current))
    return passages


def _passage(page_number: int, chunk_index: int, text: str) -> Passage:
    digest = sha256(f"{page_number}\0{chunk_index}\0{text}".encode("utf-8")).hexdigest()
    return Passage(page_number, chunk_index, text, digest)


class DocumentIndexer:
    def __init__(self, repository: SQLiteRepository, vector_index: LocalPassageIndex,
                 embedder: OllamaEmbeddingClient, *, storage_root: str | Path,
                 max_chars: int = _DEFAULT_MAX_CHARS, overlap: int = _DEFAULT_OVERLAP) -> None:
        self.repository, self.vector_index, self.embedder = repository, vector_index, embedder
        self.storage_root = Path(storage_root).resolve()
        self.max_chars, self.overlap = max_chars, overlap

    def _read_pages(self, row: dict[str, Any]) -> list[str]:
        pages: list[str] = []
        for filename in row["digitized_page_paths"]:
            path = Path(filename).resolve()
            if not path.is_relative_to(self.storage_root) or not path.is_file():
                raise ValueError("Finalized Markdown page is missing or outside storage")
            pages.append(path.read_text(encoding="utf-8"))
        return pages

    def index_document(self, document_id: str) -> dict[str, Any]:
        row = self.repository.get_document(document_id)
        if row is None:
            raise ValueError("Document not found")
        if row.get("review_status") != "finalized":
            raise ValueError("Only finalized documents can be indexed")
        try:
            pages = self._read_pages(row)
            digest = sha256("\0".join(pages).encode("utf-8")).hexdigest()
            if row.get("index_content_hash") == digest and row.get("index_status") == "indexed" \
                    and (pages and self.vector_index.count(document_id) > 0 or not pages):
                return {"document_id": document_id, "status": "indexed", "skipped": True}
            passages = split_markdown_pages(pages, self.max_chars, self.overlap)
            vectors = self.embedder.embed([passage.text for passage in passages]) if passages else []
            if len(vectors) != len(passages):
                raise ValueError("Embedding model returned a different vector count than passages")
            self.vector_index.upsert_document(document_id, list(zip(passages, vectors)))
            self.repository.set_index_status(document_id, "indexed", digest)
            return {"document_id": document_id, "status": "indexed", "skipped": False,
                    "passage_count": len(passages)}
        except Exception as exc:
            self.repository.set_index_status(document_id, "failed", error=str(exc)[:1000])
            raise

    def backfill_documents(self, *, rebuild: bool = False) -> dict[str, int]:
        if rebuild:
            self.vector_index.reset()
            rows = self.repository.list_finalized_documents()
        else:
            rows = self.repository.list_index_candidates()
        indexed = failed = 0
        for row in rows:
            try:
                self.index_document(str(row["document_id"]))
                indexed += 1
            except Exception:
                failed += 1
        return {"scanned": len(rows), "indexed": indexed, "failed": failed}
