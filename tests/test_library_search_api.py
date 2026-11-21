import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.library_search import router
from backend.api.library import router as library_router


class LibrarySearchApiTests(unittest.TestCase):
    def test_search_returns_unique_documents_without_generating_answer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "page.md"
            path.write_text("Bổ nhiệm ông A.\n\nQuyết định bổ nhiệm.", encoding="utf-8")
            indexer = SimpleNamespace(storage_root=root, embedder=None,
                vector_index=SimpleNamespace(count=lambda: 0),
                repository=SimpleNamespace(
                    list_finalized_documents=lambda: [{"document_id": "doc-1", "display_name": "Quyết định",
                        "digitized_page_paths": [str(path)], "index_status": "failed"}],
                    get_index_status=lambda: {"failed": 1}))
            with patch("backend.api.library_search._get_service", return_value=indexer), \
                    patch("backend.api.library_search.OllamaClient") as client:
                client.return_value.model = "qwen-test"
                client.return_value.chat.return_value = '{"terms":["bổ nhiệm"],"entities":[],"dates":[],"identifiers":[]}'
                response = self.client.post("/api/library/search-ai", json={"question": "bổ nhiệm"})
                self.assertEqual(client.return_value.chat.call_count, 1)
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["total"], 1)
            self.assertEqual([item["document_id"] for item in payload["results"]], ["doc-1"])
            self.assertEqual(payload["results"][0]["snippet"], "")
            self.assertEqual(payload["citations"], [])
            self.assertEqual(payload["answer"], "")

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def test_search_ai_returns_answer_sources_terms_and_page_metadata(self):
        result = {
            "answer": "Ông A được bổ nhiệm năm 2020. [Quyết định, trang 2]",
            "model": "qwen3:8b",
            "extracted_terms": {"terms": ["bổ nhiệm"], "entities": ["Ông A"], "dates": ["2020"], "identifiers": []},
            "citations": [{"document_id": "doc-1", "document_name": "Quyết định", "page_number": 2,
                           "snippet": "Bổ nhiệm ông A năm 2020.", "score": 1.5}],
            "results": [{"document_id": "doc-1", "document_name": "Quyết định", "page_number": 2,
                         "snippet": "Bổ nhiệm ông A năm 2020.", "score": 1.5}],
            "page": 0, "page_size": 20, "total": 1, "context_used_bytes": 90,
            "index_status": {"indexed": 1, "pending": 0, "failed": 0},
        }
        with patch("backend.api.library_search.run_library_search", return_value=result):
            response = self.client.post("/api/library/search-ai", json={"question": "Ông A bổ nhiệm năm nào?"})
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["answer"], result["answer"])
        self.assertEqual(payload["citations"][0]["page_number"], 2)
        self.assertEqual(payload["index_status"]["indexed"], 1)

    def test_rejects_empty_search_question(self):
        response = self.client.post("/api/library/search-ai", json={"question": " "})
        self.assertEqual(response.status_code, 422)

    def test_document_chat_routes_ai_command_to_global_search(self):
        app = FastAPI()
        app.include_router(library_router)
        client = TestClient(app)
        with patch("backend.api.library.record", return_value={"document_id": "doc-1"}), \
                patch("backend.api.library.run_library_search", return_value={"answer": "found"}) as search:
            response = client.post("/api/library/doc-1/chat", json={
                "messages": [{"role": "user", "content": "@AI: Ông A được bổ nhiệm năm nào?"}],
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["answer"], "found")
        search.assert_called_once_with("Ông A được bổ nhiệm năm nào?")


if __name__ == "__main__":
    unittest.main()
