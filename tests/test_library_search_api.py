import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.library_search import router
from backend.api.library import router as library_router


class LibrarySearchApiTests(unittest.TestCase):
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
                "messages": [{"role": "user", "content": "/AI: Ông A được bổ nhiệm năm nào?"}],
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["answer"], "found")
        search.assert_called_once_with("Ông A được bổ nhiệm năm nào?")


if __name__ == "__main__":
    unittest.main()
