import unittest
import importlib
import tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image

from backend.llm.schemas import ReviewDraft, CorrectedPage, DocumentMetadata, ReviewMarkdownPage
from backend.llm.review_store import save_review_draft

from backend.llm.markdown_review import (
    MarkdownMappingError, apply_approved_text, build_manual_markdown_review,
    build_markdown_review, preserve_protected_content,
)


class ManualFormulaTests(unittest.TestCase):
    def test_prose_edits_do_not_match_across_lines(self):
        self.assertEqual(apply_approved_text('## alpha\n\nbeta', 'alpha\n\nbeta', 'beta\n\nalpha'),
                         '## beta\n\nalpha')

    def test_prose_newline_changes_are_explicitly_rejected(self):
        for edited in ('alpha beta', 'alpha\n\n\nbeta'):
            with self.assertRaisesRegex(MarkdownMappingError, 'xuống dòng'):
                apply_approved_text('alpha\n\nbeta', 'alpha\n\nbeta', edited)

    def test_manual_formula_and_prose(self):
        raw = 'Speed $v=x$ is fast.\n\n$$ x=1 $$'
        md = '## Speed $v=x$ is fast.\n\n$$ x=1 $$'
        edited = 'Speed $v=\\frac{x}{t}$ is slow.\n\n$$ x=2 $$'
        result = build_manual_markdown_review(md, raw, edited)
        self.assertEqual(result.llm_markdown, '## ' + edited)
        self.assertEqual(apply_approved_text(md, raw, edited), result.llm_markdown)
        self.assertTrue(any(c.after == '$v=\\frac{x}{t}$' for c in result.llm_changes))

    def test_duplicate_formula_occurrence(self):
        raw = 'First $x=1$. Second $x=1$.'
        edited = 'First $x=1$. Second $x=2$.'
        self.assertEqual(build_manual_markdown_review(raw, raw, edited).llm_markdown, edited)

    def test_llm_still_protected(self):
        raw = 'Value $x=1$'
        self.assertEqual(preserve_protected_content(raw, 'Value $x=2$'), raw)
        with self.assertRaises(MarkdownMappingError):
            build_markdown_review(raw, raw, 'Value $x=2$')

    def test_disallow_formula_structure_changes(self):
        for edited in ('Value x=2', 'Value $$x=2$$', 'Value $x=2$ $y=1$'):
            with self.subTest(edited=edited), self.assertRaises(MarkdownMappingError):
                build_manual_markdown_review('Value $x=1$', 'Value $x=1$', edited)

    def test_other_protected_content_stays_locked(self):
        raw = '`x=1` and $y=1$'
        with self.assertRaises(MarkdownMappingError):
            build_manual_markdown_review(raw, raw, '`x=2` and $y=2$')

    def test_multiline_formula(self):
        raw = '$$\na=1\\\\\nb=2\n$$'
        edited = '$$\na=3\\\\\nb=4\n$$'
        self.assertEqual(build_manual_markdown_review(raw, raw, edited).llm_markdown, edited)

    def test_preview_and_finalize_both_sides_in_temporary_storage(self):
        api = importlib.import_module('backend.api.app')
        for side in ('ocr', 'llm'):
            with self.subTest(side=side), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                raw_root = root / 'data' / 'raw'
                document = raw_root / 'sample'
                document.mkdir(parents=True)
                source = document / '_source.png'
                Image.new('RGB', (20, 20), 'white').save(source)
                raw = 'Value $x=1$'
                edited = 'Value $x=\\frac{2}{3}$'
                draft = ReviewDraft('formula_test', 'sample', str(source), str(document), 1,
                    [CorrectedPage('page_001', raw, raw)],
                    DocumentMetadata('0', 'unclassified', None, None, None, 'text'),
                    markdown_pages=[ReviewMarkdownPage('page_001', raw, raw, [])])
                save_review_draft(document, draft, [])
                with patch.object(api, 'OUTPUT_ROOT', raw_root), patch.object(api, 'REPOSITORY_ROOT', root):
                    preview = api.preview_llm_review(draft.review_id, api.ReviewPreviewRequest(
                        pages={'page_001': {'ocr_text': edited, 'llm_text': edited}}))['pages'][0]
                    self.assertEqual(preview['ocr_markdown'], edited)
                    self.assertEqual(preview['llm_markdown'], edited)
                    self.assertTrue(preview['ocr_manual_changes'])
                    self.assertTrue(preview['llm_manual_changes'])
                    saved = api.finalize_llm_review(draft.review_id, api.FinalizeReviewRequest(
                        source=side, approved_pages={'page_001': edited}, edit_log=[{
                            'actor': 'user', 'content_type': 'formula',
                            'page_id': 'page_001', 'source_side': side, 'timestamp': '2026-11-05T00:00:00Z',
                            'before': '$x=1$', 'after': '$x=\\frac{2}{3}$',
                            'mirrored_before': '$x=1$', 'mirrored_after': '$x=\\frac{2}{3}$',
                        }]))
                    self.assertEqual(Path(saved['digitized_page_paths'][0]).read_text(), edited)
                    log_text = Path(saved['edit_log_path']).read_text()
                    self.assertIn('mirrored_after', log_text)
                    self.assertIn('"actor": "user"', log_text)
                    self.assertIn('"content_type": "formula"', log_text)


if __name__ == '__main__':
    unittest.main()
