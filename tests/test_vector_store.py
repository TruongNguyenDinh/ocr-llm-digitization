import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.llm.embedding_client import OllamaEmbeddingClient
from backend.llm.ollama_client import OllamaError
from backend.llm.vector_store import LocalPassageIndex, Passage


class VectorStoreTests(unittest.TestCase):
    def test_ollama_embedding_client_batches_and_validates_vectors(self):
        client = OllamaEmbeddingClient(base_url="http://ollama", model="embed-test")
        with patch.object(client._client, "_request", return_value={"embeddings": [[1, 0], [0, 1]]}) as request:
            self.assertEqual(client.embed(["first", "second"]), [[1.0, 0.0], [0.0, 1.0]])
        request.assert_called_once_with("/api/embed", {"model": "embed-test", "input": ["first", "second"]})
        with patch.object(client._client, "_request", return_value={"embeddings": [[1, 0]]}):
            with self.assertRaisesRegex(OllamaError, "count"):
                client.embed(["first", "second"])

    def test_persistent_upsert_is_idempotent_and_search_can_filter_and_delete(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "vectors"
            passage = Passage(page_number=2, chunk_index=0, text="Ông A được bổ nhiệm năm 2020", content_hash="hash-a")
            index = LocalPassageIndex(path, vector_size=3)
            index.upsert_document("doc-a", [(passage, [1, 0, 0])])
            index.upsert_document("doc-a", [(passage, [1, 0, 0])])
            index.upsert_document("doc-b", [(Passage(1, 0, "Khác", "hash-b"), [0, 1, 0])])
            self.assertEqual(index.count(), 2)
            self.assertEqual([item.document_id for item in index.search([1, 0, 0], limit=10)], ["doc-a", "doc-b"])
            self.assertEqual([item.document_id for item in index.search([0, 1, 0], document_id="doc-a")], ["doc-a"])
            index.close()

            reopened = LocalPassageIndex(path, vector_size=3)
            self.assertEqual(reopened.count("doc-a"), 1)
            reopened.delete_document("doc-a")
            self.assertEqual(reopened.count(), 1)
            reopened.close()


if __name__ == "__main__":
    unittest.main()
