import json
import tempfile
import unittest
from pathlib import Path

from backend.llm.library_search import LibrarySearchService, answer_library_question, extract_search_query
from backend.llm.document_index import split_markdown_pages
from backend.llm.vector_store import ScoredPassage


class FakeClient:
    model = "qwen-test"
    def __init__(self, content): self.content, self.calls = content, []
    def chat(self, messages, response_format=None, **kwargs):
        self.calls.append((messages, response_format))
        return self.content


class FakeRepository:
    def __init__(self, rows): self.rows = rows
    def list_finalized_documents(self): return self.rows


class FakeIndex:
    def __init__(self, results): self.results, self.calls = results, []
    def count(self): return len(self.results)
    def search(self, vector, **kwargs):
        self.calls.append((vector, kwargs))
        return self.results


class FakeEmbedder:
    def __init__(self, client=None): self.calls, self.client = [], client
    def embed(self, texts): self.calls.append(list(texts)); return [[1.0, 0.0] for _ in texts]


class LibrarySearchTests(unittest.TestCase):
    def test_extraction_preserves_only_question_facts_and_falls_back_on_invalid_json(self):
        client = FakeClient(json.dumps({"terms": ["bổ nhiệm"], "entities": ["Nguyễn Văn A"],
                                        "dates": ["2020"], "identifiers": []}, ensure_ascii=False))
        terms = extract_search_query("Ông Nguyễn Văn A được bổ nhiệm năm 2020?", client)
        self.assertEqual(terms.entities, ["Nguyễn Văn A"])
        self.assertEqual(terms.dates, ["2020"])
        self.assertIn("bổ nhiệm", terms.terms)
        malformed = extract_search_query("Thạch Sanh", FakeClient("not json"))
        self.assertIn("sanh", malformed.terms)

    def test_hybrid_search_ranks_exact_lexical_match_and_paginates_all_documents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = []
            target_text = "Ông Nguyễn Văn A được bổ nhiệm năm 2020."
            target_hash = split_markdown_pages([target_text])[0].content_hash
            for index in range(25):
                path = root / f"{index}.md"
                text = target_text if index == 0 else f"Tài liệu khác số {index}."
                path.write_text(text, encoding="utf-8")
                rows.append({"document_id": f"doc-{index}", "display_name": f"Tài liệu {index}",
                             "review_status": "finalized", "index_status": "indexed",
                             "digitized_page_paths": [str(path)]})
            query_client = FakeClient(json.dumps({"terms": ["bổ nhiệm", "2020"], "entities": ["Nguyễn Văn A"],
                                                  "dates": ["2020"], "identifiers": []}, ensure_ascii=False))
            embedder, index = FakeEmbedder(), FakeIndex([ScoredPassage(
                "doc-0", 1, 0, target_text, target_hash, 0.82)])
            service = LibrarySearchService(FakeRepository(rows), index, embedder, query_client, storage_root=root,
                                           vector_score_threshold=0.5)
            page = service.search_library("Ông Nguyễn Văn A được bổ nhiệm năm 2020?", page=0, page_size=10)
            self.assertEqual(page.total, 1)
            self.assertEqual(page.results[0].document_id, "doc-0")
            self.assertEqual(embedder.calls, [["Ông Nguyễn Văn A được bổ nhiệm năm 2020? bổ nhiệm 2020 Nguyễn Văn A"]])
            self.assertEqual(len(query_client.calls), 1)
            self.assertEqual(index.calls[0][1]["limit"], 1)

    def test_lexical_results_are_not_cut_off_at_a_fixed_document_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = []
            for index in range(25):
                path = root / f"{index}.md"
                path.write_text("công văn bổ nhiệm", encoding="utf-8")
                rows.append({"document_id": f"doc-{index}", "display_name": f"Doc {index}", "review_status": "finalized",
                             "digitized_page_paths": [str(path)], "index_status": "pending"})
            service = LibrarySearchService(FakeRepository(rows), FakeIndex([]), FakeEmbedder(),
                                           FakeClient('{"terms":["bổ nhiệm"],"entities":[],"dates":[],"identifiers":[]}'),
                                           storage_root=root)
            page = service.search_library("tìm văn bản bổ nhiệm", page=1, page_size=10)
            self.assertEqual(page.total, 25)
            self.assertEqual(len(page.results), 10)
            self.assertEqual(page.page, 1)

    def test_answer_without_evidence_does_not_call_model(self):
        client = FakeClient("unexpected")
        result = answer_library_question("Năm nào?", [], client)
        self.assertEqual(result.answer, "Chưa tìm thấy tài liệu có căn cứ phù hợp để trả lời câu hỏi này.")
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
