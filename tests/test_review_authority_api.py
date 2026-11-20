import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from fastapi.testclient import TestClient

api = importlib.import_module('backend.api.app')


class ReviewAuthorityApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        self.draft = SimpleNamespace(
            pages=[SimpleNamespace(page_id='page_001', raw_text='OCR', corrected_text='LLM')],
            markdown_pages=[SimpleNamespace(page_id='page_001', ocr_markdown='OCR',
                llm_markdown='LLM', llm_changes=[{'start': 0, 'end': 3, 'before_start': 0,
                'before_end': 3, 'before': 'OCR', 'after': 'LLM'}])],
        )

    def test_preview_and_finalize_keep_human_markdown_exactly(self):
        approved = '# Người dùng\n\n$$x=2$$\n\n[Liên kết](https://example.com)'
        with patch.object(api, 'load_review_draft', return_value=self.draft):
            response = self.client.post('/api/llm/reviews/test/preview', json={
                'content_format': 'markdown', 'pages': {'page_001': {'ocr_text': 'OCR', 'llm_text': approved}}})
            self.assertEqual(response.status_code, 200, response.text)
            page = response.json()['pages'][0]
            self.assertEqual(page['llm_markdown'], approved)
            self.assertTrue(page['llm_manual_changes'])
            with patch.object(api, 'finalize_review', return_value={'saved': True}) as finalize:
                response = self.client.post('/api/llm/reviews/test/finalize', json={
                    'content_format': 'markdown', 'source': 'llm', 'approved_pages': {'page_001': approved}})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(finalize.call_args.args[2], {'page_001': approved})

    def test_original_image_and_pdf_pages(self):
        with TemporaryDirectory() as directory:
            image = Image.new('RGB', (120, 200), 'white')
            for extension in ('png', 'pdf'):
                source = Path(directory) / f'original.{extension}'
                image.save(source)
                self.draft.source_path = str(source)
                with patch.object(api, 'load_review_draft', return_value=self.draft):
                    response = self.client.get('/api/llm/reviews/test/original/page_001')
                    self.assertEqual(response.status_code, 200, response.text[:80])
                    self.assertTrue(response.content.startswith(b'\x89PNG'))
                    self.assertEqual(self.client.get('/api/llm/reviews/test/original/page_999').status_code, 404)
            image.close()
