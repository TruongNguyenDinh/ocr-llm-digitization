import unittest

from backend.llm.correction_guard import constrain_corrections
from backend.llm.markdown_review import preserve_protected_content


class CorrectionGuardTests(unittest.TestCase):
    def test_reject_word_replacement_but_keep_valid_accent(self):
        self.assertEqual(constrain_corrections("Thạch Sanh thấu to", "Thạch và thấu tỏ"),
                         "Thạch Sanh thấu tỏ")

    def test_reject_punctuation_and_spacing_changes(self):
        for proposal in ["Th,ạch Sanh", "Thạch, Sanh", "Thạch  Sanh", "Thạch\nSanh"]:
            with self.subTest(proposal=proposal):
                self.assertEqual(constrain_corrections("Thạch Sanh", proposal), "Thạch Sanh")

    def test_reject_synonym_and_proper_name_replacement(self):
        self.assertEqual(constrain_corrections("thấu to", "thấu hiểu"), "thấu to")
        self.assertEqual(constrain_corrections("Sanh", "Xanh"), "Sanh")

    def test_allow_one_letter_and_accents(self):
        for before, after in [("chươg", "chương"), ("biếtt", "biết"), ("tõi", "tôi"),
                              ("Thach", "Thạch"), ("duong", "đường")]:
            with self.subTest(before=before):
                self.assertEqual(constrain_corrections(before, after), after)

    def test_keep_numbers_and_line_boundaries(self):
        self.assertEqual(constrain_corrections("123\nthấu to", "124\nthấu tỏ"), "123\nthấu tỏ")

    def test_protected_content_stays_unchanged(self):
        original = "`to` $to$ [to](to) <b>thấu to</b>"
        proposal = "`tỏ` $tỏ$ [tỏ](tỏ) <b>thấu tỏ</b>"
        self.assertEqual(preserve_protected_content(original, constrain_corrections(original, proposal)),
                         "`to` $to$ [to](to) <b>thấu tỏ</b>")
