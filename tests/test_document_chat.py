import unittest
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi import HTTPException
from backend.llm.document_chat import MAX_CHAT_CONTEXT_BYTES, chat_context_bytes, chat_with_document


class DocumentChatTests(unittest.TestCase):
    def test_retrieves_relevant_page_from_long_document(self):
        model = Mock(model='qwen3:8b')
        model.chat.return_value = 'Thông tin ở trang 8.'
        pages = [f'Nội dung không liên quan trang {n}. ' * 90 for n in range(1, 8)]
        pages.append('Quy định mức hỗ trợ là 20 triệu đồng cho mỗi doanh nghiệp.')
        history = [{'role': 'user', 'content': 'Mức hỗ trợ là bao nhiêu?'}]
        answer, name, used = chat_with_document('Tài liệu A', pages, history, model)
        sent = model.chat.call_args.args[0]
        self.assertIn('Trang 8', sent[0]['content'])
        self.assertIn('20 triệu đồng', sent[0]['content'])
        self.assertNotIn('Nội dung không liên quan trang 1', sent[0]['content'])
        self.assertEqual(sent[1:], history)
        self.assertEqual(name, 'qwen3:8b')
        self.assertEqual(answer, 'Thông tin ở trang 8.')
        self.assertEqual(used, chat_context_bytes(pages, history, 'Tài liệu A'))
        self.assertLessEqual(used, MAX_CHAT_CONTEXT_BYTES)

    def test_long_document_with_many_pages_fits_context(self):
        model = Mock(model='qwen3:8b')
        model.chat.return_value = 'Có thông tin.'
        pages = [f'Trang {n}. Chủ đề khác nhau trong văn bản. ' * 100 for n in range(1, 100)]
        pages.append('Trang 100. Quy định quyền lợi hỗ trợ hộ kinh doanh.')
        _answer, _name, used = chat_with_document('A', pages, [{'role': 'user', 'content': 'quyền lợi'}], model)
        self.assertLessEqual(used, MAX_CHAT_CONTEXT_BYTES)
        self.assertIn('Trang 100', model.chat.call_args.args[0][0]['content'])

    def test_empty_history_does_not_send_entire_document(self):
        model = Mock(model='qwen3:8b')
        with self.assertRaises(ValueError):
            chat_with_document('A', ['Văn bản'], [], model)
        model.chat.assert_not_called()

    def test_question_is_required_before_calling_model(self):
        model = Mock()
        with self.assertRaises(ValueError):
            chat_with_document('A', ['x' * 25000], [], model)
        model.chat.assert_not_called()


class DocumentChatApiTests(unittest.TestCase):
    def test_missing_selection_does_not_call_model(self):
        library = importlib.import_module('backend.api.library')
        app = importlib.import_module('backend.api.app').app
        with patch.object(library, 'record', side_effect=HTTPException(404, 'Document not found')), patch.object(library, 'chat_with_document') as chat:
            self.assertEqual(TestClient(app).post('/api/library/missing/chat', json={'messages': []}).status_code, 404)
            chat.assert_not_called()

    def test_uses_selected_stored_document(self):
        library = importlib.import_module('backend.api.library')
        app = importlib.import_module('backend.api.app').app
        with TemporaryDirectory() as directory:
            page = Path(directory) / 'page_001.md'
            page.write_text('Nội dung người dùng đã duyệt', encoding='utf-8')
            row = {'source_path': '/example/selected.pdf', 'document_id': 'selected', 'label_name': 'letter', 'page_count': 1, 'created_at': '', 'digitized_page_paths': json.dumps([str(page)])}
            with patch.object(library, 'record', return_value=row), patch.object(library, 'safe_file', return_value=page), patch.object(library, 'chat_with_document', return_value=('Đã sẵn sàng', 'qwen3:8b', 200)) as chat:
                history = [{'role': 'user', 'content': 'Hỏi về tài liệu'}]
                response = TestClient(app).post('/api/library/selected/chat', json={'messages': history})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(chat.call_args.args, ('selected', ['Nội dung người dùng đã duyệt'], history))
                self.assertEqual(response.json()['document_id'], 'selected')
