import tempfile
import unittest
from pathlib import Path

from backend.llm.document_index import DocumentIndexer, split_markdown_pages
from backend.llm.vector_store import Passage
from backend.storage.repository import SQLiteRepository


class FakeRepository:
    def __init__(self, row):
        self.row = row
        self.status = "pending"
        self.content_hash = ""
        self.error = None

    def get_document(self, document_id):
        if not self.row or self.row["document_id"] != document_id:
            return None
        return {**self.row, "index_status": self.status, "index_content_hash": self.content_hash}

    def set_index_status(self, document_id, status, content_hash="", error=None):
        self.status, self.content_hash, self.error = status, content_hash, error

    def get_index_status(self):
        return {"indexed": int(self.status == "indexed"), "pending": int(self.status == "pending"),
                "failed": int(self.status == "failed")}

    def list_index_candidates(self):
        return [self.row] if self.status in {"pending", "failed"} else []
    def list_finalized_documents(self):
        return [self.row] if self.row and self.row.get("review_status") == "finalized" else []


class FakeIndex:
    def __init__(self):
        self.items = {}
        self.upserts = 0
    def upsert_document(self, document_id, passages):
        self.items[document_id] = passages
        self.upserts += 1
    def count(self, document_id=None):
        return len(self.items.get(document_id, [])) if document_id else sum(map(len, self.items.values()))
    def delete_document(self, document_id):
        self.items.pop(document_id, None)
    def reset(self):
        self.items.clear()


class FakeEmbedder:
    def __init__(self):
        self.fail = False
    def embed(self, texts):
        if self.fail:
            raise RuntimeError("embedding unavailable")
        return [[float(index + 1), 1.0, 0.5] for index, _ in enumerate(texts)]


class DocumentIndexTests(unittest.TestCase):
    def test_repository_migration_adds_pending_index_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = SQLiteRepository(Path(temporary) / "metadata.sqlite3")
            document_columns = {row[1] for row in __import__("sqlite3").connect(repository.database_path)
                                .execute("PRAGMA table_info(documents)")}
            self.assertTrue({"index_status", "index_content_hash", "index_error", "indexed_at"} <= document_columns)

    def test_chunking_preserves_page_number_and_stable_hashes(self):
        pages = ["First paragraph.\n\nSecond paragraph.", "Third page."]
        chunks = split_markdown_pages(pages, max_chars=25, overlap=3)
        self.assertTrue(all(isinstance(chunk, Passage) for chunk in chunks))
        self.assertEqual([chunk.page_number for chunk in chunks], [1, 1, 2])
        self.assertEqual(chunks, split_markdown_pages(pages, max_chars=25, overlap=3))
        self.assertTrue(all(chunk.content_hash for chunk in chunks))

    def test_index_skips_unchanged_content_and_backfill_retries_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            page_path = root / "page.md"
            page_path.write_text("Ông A được bổ nhiệm năm 2020.", encoding="utf-8")
            row = {"document_id": "doc-1", "review_status": "finalized",
                   "digitized_page_paths": [str(page_path)]}
            repo, index, embedder = FakeRepository(row), FakeIndex(), FakeEmbedder()
            service = DocumentIndexer(repo, index, embedder, storage_root=root)
            self.assertEqual(service.index_document("doc-1")["status"], "indexed")
            service.index_document("doc-1")
            self.assertEqual(index.upserts, 1)
            page_path.write_text("Nội dung đã được sửa.", encoding="utf-8")
            service.index_document("doc-1")
            self.assertEqual(index.upserts, 2)
            embedder.fail = True
            repo.status = "pending"
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                service.index_document("doc-1")
            self.assertEqual(repo.status, "failed")
            embedder.fail = False
            result = service.backfill_documents()
            self.assertEqual(result["indexed"], 1)
            self.assertEqual(repo.status, "indexed")

    def test_refuses_non_finalized_documents(self):
        repo = FakeRepository({"document_id": "draft", "review_status": "pending_review"})
        service = DocumentIndexer(repo, FakeIndex(), FakeEmbedder(), storage_root=".")
        with self.assertRaisesRegex(ValueError, "finalized"):
            service.index_document("draft")

    def test_rebuild_recreates_vectors_for_already_indexed_documents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            page_path = root / "page.md"
            page_path.write_text("Nội dung văn bản.", encoding="utf-8")
            repo = FakeRepository({"document_id": "doc-1", "review_status": "finalized",
                                   "digitized_page_paths": [str(page_path)]})
            index = FakeIndex()
            service = DocumentIndexer(repo, index, FakeEmbedder(), storage_root=root)
            service.index_document("doc-1")
            result = service.backfill_documents(rebuild=True)
            self.assertEqual(result["indexed"], 1)
            self.assertEqual(index.upserts, 2)


if __name__ == "__main__":
    unittest.main()
