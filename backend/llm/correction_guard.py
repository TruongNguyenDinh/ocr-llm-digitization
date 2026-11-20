"""Conservative limits for automatic OCR corrections (not human edits)."""

import re
import unicodedata


def _base_letters(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    ).replace("đ", "d").replace("Đ", "D")


def _one_edit(before: str, after: str) -> bool:
    if len(before) == len(after):
        return sum(a != b for a, b in zip(before, after)) <= 1
    if abs(len(before) - len(after)) != 1:
        return False
    shorter, longer = sorted((before, after), key=len)
    index = next((i for i, char in enumerate(shorter) if char != longer[i]), len(shorter))
    return shorter[index:] == longer[index + 1:]


def constrain_corrections(raw_text: str, corrected_text: str) -> str:
    """Keep separators exact; accept diacritics or one letter edit per word.

    Ambiguous token alignment reverts the entire affected line. Capitalized
    words permit diacritics only to conservatively protect proper names.
    """
    raw_lines = re.split(r"(\r\n|\r|\n)", raw_text)
    new_lines = re.split(r"(\r\n|\r|\n)", corrected_text)
    if len(raw_lines) != len(new_lines) or raw_lines[1::2] != new_lines[1::2]:
        return raw_text
    for index in range(0, len(raw_lines), 2):
        original = re.split(r"(\w+)", unicodedata.normalize("NFC", raw_lines[index]))
        proposed = re.split(r"(\w+)", unicodedata.normalize("NFC", new_lines[index]))
        if len(original) != len(proposed) or original[::2] != proposed[::2]:
            continue
        changed = False
        for word_index in range(1, len(original), 2):
            before, after = original[word_index], proposed[word_index]
            if before == after or not before.isalpha() or not after.isalpha():
                continue
            base_before, base_after = _base_letters(before), _base_letters(after)
            allowed = base_before == base_after or (
                before.islower() and after.islower() and _one_edit(base_before, base_after)
            )
            if allowed:
                original[word_index] = after
                changed = True
        if changed:
            raw_lines[index] = "".join(original)
    return "".join(raw_lines)
