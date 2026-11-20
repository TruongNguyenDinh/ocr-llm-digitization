import unittest

from backend.llm.markdown_review import build_human_markdown_review, shift_llm_changes


class HumanMarkdownReviewTests(unittest.TestCase):
    def test_human_can_override_llm_formula_and_structure(self):
        before = '# LLM sai\n\n$x=1$'
        after = '# Người dùng quyết định\n\n$$x=2$$\n\nĐoạn mới'
        result = build_human_markdown_review(before, after)
        self.assertEqual(result.llm_markdown, after)
        self.assertTrue(result.llm_changes)

    def test_reverted_edit_has_no_changes(self):
        self.assertEqual(build_human_markdown_review('anh đó', 'anh đó').llm_changes, [])

    def test_user_replacement_removes_model_highlight(self):
        manual = build_human_markdown_review('LLM sai', 'Người dùng sửa')
        self.assertEqual(shift_llm_changes([{'start': 0, 'end': 7}], manual.llm_changes), [])
