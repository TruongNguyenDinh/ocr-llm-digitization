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
    def test_document_results_are_deduplicated_before_pagination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = []
            for index in range(3):
                path = root / f"{index}.md"
                path.write_text("Bổ nhiệm cán bộ.\n\nQuyết định bổ nhiệm mới.", encoding="utf-8")
                rows.append({"document_id": f"doc-{index}", "display_name": f"Tài liệu {index}",
                             "digitized_page_paths": [str(path)], "index_status": "failed"})
            service = LibrarySearchService(FakeRepository(rows), FakeIndex([]), FakeEmbedder(),
                FakeClient('{"terms":["bổ nhiệm"],"entities":[],"dates":[],"identifiers":[]}'), storage_root=root)
            pages = [service.search_library("bổ nhiệm", page=index, page_size=1, documents_only=True)
                     for index in range(3)]
            self.assertEqual([page.total for page in pages], [3, 3, 3])
            self.assertEqual({page.results[0].document_id for page in pages}, {"doc-0", "doc-1", "doc-2"})

    def test_person_with_title_matches_separate_signature_and_decision_pages(self):
        for signature in ("Nguyễn Xuân Phúc\n\nTHỦ TƯỚNG", "NGUYỄN  XUÂN\nPHÚC\nTHỦ TƯỚNG"):
            with self.subTest(signature=signature), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                rows = []
                for document_id, pages in {
                    "decision": ["THỦ TƯỚNG CHÍNH PHỦ\n\nSố: 81/QĐ-TTg\n\nNgày 19 tháng 01 năm 2021\n\nQUYẾT ĐỊNH phê duyệt Chương trình hỗ trợ pháp lý.", signature],
                    "unrelated": ["QUYẾT ĐỊNH khác. Thủ tướng Nguyễn Tấn Dũng đã ký."],
                    "partial-name": ["QUYẾT ĐỊNH khác. Nguyễn Xuân PhúcAnh."],
                }.items():
                    paths = []
                    for number, content in enumerate(pages):
                        path = root / f"{document_id}-{number}.md"
                        path.write_text(content, encoding="utf-8")
                        paths.append(str(path))
                    rows.append({"document_id": document_id, "display_name": document_id,
                                 "index_status": "failed", "digitized_page_paths": paths})
                client = FakeClient(json.dumps({"terms": ["quyết định"],
                    "entities": ["Thủ Tướng Nguyễn Xuân Phúc"], "dates": [], "identifiers": []}))
                service = LibrarySearchService(FakeRepository(rows), FakeIndex([]), FakeEmbedder(),
                                               client, storage_root=root)

                result = service.search_library("Thủ Tướng Nguyễn Xuân Phúc đã ký những quyết định nào ?")

                self.assertEqual({item.document_id for item in result.results}, {"decision"})
                self.assertEqual({item.page_number for item in result.results}, {1, 2})
                self.assertTrue(any("81/QĐ-TTg" in item.snippet and "QUYẾT ĐỊNH" in item.snippet
                                    for item in result.results if item.page_number == 1))

    def test_extraction_preserves_only_question_facts_and_falls_back_on_invalid_json(self):
        client = FakeClient(json.dumps({"terms": ["bổ nhiệm"], "entities": ["Nguyễn Văn A"],
                                        "dates": ["2020"], "identifiers": []}, ensure_ascii=False))
        terms = extract_search_query("Ông Nguyễn Văn A được bổ nhiệm năm 2020?", client)
        self.assertEqual(terms.entities, ["Nguyễn Văn A"])
        self.assertEqual(terms.dates, ["2020"])
        self.assertIn("bổ nhiệm", terms.terms)
        malformed = extract_search_query("Thạch Sanh", FakeClient("not json"))
        self.assertIn("sanh", malformed.terms)

    def test_promotes_capitalized_name_from_terms_to_entity(self):
        client = FakeClient('{"terms":["Lý Thông"],"entities":[],"dates":[],"identifiers":[]}')

        result = extract_search_query("Lý Thông phải chịu hậu quả gì?", client)

        self.assertIn("Lý Thông", result.entities)

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

    def test_named_entity_match_ranks_story_above_common_legal_terms(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legal_path = root / "legal.md"
            legal_path.write_text("Cơ quan phải chịu hậu quả qua quá trình hỗ trợ pháp lý.", encoding="utf-8")
            story_path = root / "story.md"
            story_path.write_text("Lý Thông bị sét đánh chết vì tội ác của mình.", encoding="utf-8")
            rows = [
                {"document_id": "legal", "display_name": "Văn bản pháp lý", "source_path": str(root / "_source.pdf"),
                 "review_status": "finalized", "index_status": "failed", "digitized_page_paths": [str(legal_path)]},
                {"document_id": "story", "display_name": "Truyện Thạch Sanh", "source_path": str(root / "_source.pdf"),
                 "review_status": "finalized", "index_status": "failed", "digitized_page_paths": [str(story_path)]},
            ]
            extraction = FakeClient('{"terms":["hậu quả"],"entities":["Lý Thông"],"dates":[],"identifiers":[]}')
            service = LibrarySearchService(FakeRepository(rows), FakeIndex([]), FakeEmbedder(), extraction,
                                           storage_root=root)

            result = service.search_library("Lý Thông phải chịu hậu quả gì?")

            self.assertEqual(result.results[0].document_id, "story")
            self.assertEqual({item.document_id for item in result.results}, {"story"})

    def test_vector_results_from_documents_with_failed_index_status_are_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            page_path = root / "page.md"
            page_path.write_text("Nội dung được lưu.", encoding="utf-8")
            row = {"document_id": "failed-doc", "display_name": "Tài liệu lỗi", "source_path": str(root / "doc.pdf"),
                   "review_status": "finalized", "index_status": "failed", "digitized_page_paths": [str(page_path)]}
            stale = ScoredPassage("failed-doc", 1, 0, "Đoạn vector cũ không còn hợp lệ", "old-hash", 0.95)
            service = LibrarySearchService(FakeRepository([row]), FakeIndex([stale]), FakeEmbedder(),
                                           FakeClient('{"terms":["từ khóa"],"entities":[],"dates":[],"identifiers":[]}'),
                                           storage_root=root)

            result = service.search_library("từ khóa không có trong tài liệu")

            self.assertEqual(result.results, [])

    def test_empty_display_name_uses_document_folder_instead_of_source_filename(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "government_document"
            folder.mkdir()
            page_path = root / "page.md"
            page_path.write_text("Quyết định số 12.", encoding="utf-8")
            row = {"document_id": "doc", "display_name": "", "source_path": str(folder / "_source.pdf"),
                   "review_status": "finalized", "index_status": "pending", "digitized_page_paths": [str(page_path)]}
            service = LibrarySearchService(FakeRepository([row]), FakeIndex([]), FakeEmbedder(),
                                           FakeClient('{"terms":["Quyết định"],"entities":[],"dates":[],"identifiers":[]}'),
                                           storage_root=root)

            result = service.search_library("Quyết định số 12")

            self.assertEqual(result.results[0].document_name, "government_document")


if __name__ == "__main__":
    unittest.main()
