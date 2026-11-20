from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import re


class MarkdownMappingError(ValueError):
    """Raised when a text-only LLM edit cannot safely map onto OCR Markdown."""


@dataclass(frozen=True)
class MarkdownChange:
    start: int
    end: int
    before: str
    after: str
    before_start: int
    before_end: int

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


@dataclass(frozen=True)
class MarkdownReview:
    ocr_markdown: str
    llm_markdown: str
    llm_changes: list[MarkdownChange]

    def to_dict(self) -> dict[str, object]:
        return {
            "ocr_markdown": self.ocr_markdown,
            "llm_markdown": self.llm_markdown,
            "llm_changes": [change.to_dict() for change in self.llm_changes],
        }


def _escape_markdown_text(text: str) -> str:
    return re.sub(r"([\\`*_{}\[\]<>()#+.!|~$])", r"\\\1", text)


def _protected_spans(markdown: str, *, include_math: bool = True) -> list[tuple[int, int]]:
    patterns = (
        r"!?\[[^\]]*\]\((?:[^()]|\([^()]*\))*\)",
        r"```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`",
        r"<[^>]+>",
    )
    spans = [
        (match.start(), match.end())
        for pattern in patterns
        for match in re.finditer(pattern, markdown)
    ]
    if include_math:
        spans.extend((m.start(), m.end()) for m in _formula_matches(markdown))
    return spans


def _formula_matches(text: str) -> list[re.Match[str]]:
    protected = _protected_spans(text, include_math=False)
    return [m for m in re.finditer(r"(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$|(?<![\\$])\$(?!\$)(?:\\.|[^$\n\\])+(?<!\\)\$(?!\$)", text)
            if not _overlaps_protected(m.start(), m.end(), protected)]


def _overlaps_protected(start: int, end: int, protected: list[tuple[int, int]]) -> bool:
    if start == end:
        return any(protected_start <= start <= protected_end for protected_start, protected_end in protected)
    return any(start < protected_end and end > protected_start for protected_start, protected_end in protected)


def _find_all(text: str, needle: str) -> list[int]:
    if not needle:
        return []
    positions: list[int] = []
    cursor = 0
    while True:
        position = text.find(needle, cursor)
        if position < 0:
            return positions
        positions.append(position)
        cursor = position + 1


def _locate_replacement(
    markdown: str,
    raw_text: str,
    raw_start: int,
    raw_end: int,
    old_text: str,
) -> tuple[int, int]:
    if "\n" in old_text or "\n" in raw_text[raw_start:raw_end]:
        raise MarkdownMappingError("LLM correction attempted to change page line structure.")

    # Never relocate an edit inside a formula/link/code span to similar prose.
    if _overlaps_protected(raw_start, raw_end, _protected_spans(raw_text)):
        raise MarkdownMappingError("Correction attempted to change protected OCR content (formula, link, code or HTML).")

    protected = _protected_spans(markdown)
    # Anchor the whole source line before searching for a short diff fragment.
    # This preserves offsets for repeated spaces and characters, even when
    # Markdown adds a heading marker or wraps the line in HTML.
    line_start = raw_text.rfind("\n", 0, raw_start) + 1
    line_end = raw_text.find("\n", raw_end)
    if line_end == -1:
        line_end = len(raw_text)
    line = raw_text[line_start:line_end]
    if line.strip():
        anchors = _find_all(markdown, line)
        if len(anchors) == 1:
            start = anchors[0] + raw_start - line_start
            end = anchors[0] + raw_end - line_start
            if _overlaps_protected(start, end, protected):
                raise MarkdownMappingError("Correction attempted to change protected OCR Markdown content.")
            return start, end

    if old_text:
        candidates = [
            position for position in _find_all(markdown, old_text)
            if not _overlaps_protected(position, position + len(old_text), protected)
        ]
        if not candidates:
            raise MarkdownMappingError(
                f"Could not map corrected OCR text onto Markdown: {old_text[:80]!r}"
            )
        if len(candidates) == 1:
            return candidates[0], candidates[0] + len(old_text)

        left = raw_text[max(0, raw_start - 32):raw_start]
        right = raw_text[raw_end:raw_end + 32]
        scored: list[tuple[int, int, int]] = []
        for candidate in candidates:
            before = markdown[max(0, candidate - len(left)):candidate]
            after = markdown[candidate + len(old_text):candidate + len(old_text) + len(right)]
            score = SequenceMatcher(None, left, before, autojunk=False).ratio()
            score += SequenceMatcher(None, right, after, autojunk=False).ratio()
            scored.append((score, candidate, candidate + len(old_text)))
        scored.sort(reverse=True)
        if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.08:
            raise MarkdownMappingError(
                f"Correction is ambiguous in Markdown; repeated text {old_text[:80]!r}."
            )
        return scored[0][1], scored[0][2]

    left = raw_text[max(0, raw_start - 24):raw_start]
    right = raw_text[raw_end:raw_end + 24]
    candidates: list[int] = []
    protected = _protected_spans(markdown)
    if not left:
        for right_size in range(len(right), 0, -1):
            candidates = [
                position for position in _find_all(markdown, right[:right_size])
                if not _overlaps_protected(position, position, protected)
            ]
            if candidates:
                break
        if len(candidates) != 1:
            raise MarkdownMappingError("Could not unambiguously locate an LLM insertion at the start of Markdown.")
        return candidates[0], candidates[0]
    for left_size in range(len(left), 0, -1):
        suffix = left[-left_size:]
        for left_position in _find_all(markdown, suffix):
            boundary = left_position + left_size
            if _overlaps_protected(boundary, boundary, protected):
                continue
            if not right:
                candidates.append(boundary)
                continue
            for right_size in range(min(len(right), 24), 0, -1):
                prefix = right[:right_size]
                if markdown.startswith(prefix, boundary):
                    candidates.append(boundary)
                    break
            if candidates:
                break
        if candidates:
            break
    if len(set(candidates)) != 1:
        raise MarkdownMappingError("Could not unambiguously locate an LLM insertion in Markdown.")
    boundary = candidates[0]
    return boundary, boundary


def _text_diff(raw_text: str, corrected_text: str) -> list[tuple[int, int, str, str]]:
    matcher = SequenceMatcher(None, raw_text, corrected_text, autojunk=False)
    return [
        (i1, i2, raw_text[i1:i2], corrected_text[j1:j2])
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    ]


def preserve_protected_content(raw_text: str, corrected_text: str) -> str:
    """Keep OCR line breaks, formulas, links, code and HTML in LLM suggestions.

    Revert any edit touching a protected span, including edits crossing its
    boundary, so a partial formula can never be accepted accidentally.
    """
    protected = _protected_spans(raw_text)
    chunks: list[str] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(
        None, raw_text, corrected_text, autojunk=False
    ).get_opcodes():
        before = raw_text[i1:i2]
        after = corrected_text[j1:j2]
        changes_lines = any(char in before or char in after for char in "\r\n")
        if tag == "equal" or changes_lines or _overlaps_protected(i1, i2, protected):
            chunks.append(raw_text[i1:i2])
        else:
            chunks.append(corrected_text[j1:j2])
    return "".join(chunks)


def _apply_text_changes(
    markdown: str,
    raw_text: str,
    corrected_text: str,
) -> MarkdownReview:
    edits: list[tuple[int, int, str, str]] = []
    # Anchor differences within each original line. A page-wide matcher can
    # align repeated words across lines and mistake prose edits for line moves.
    raw_lines = re.split(r"(\r\n|\r|\n)", raw_text)
    corrected_lines = re.split(r"(\r\n|\r|\n)", corrected_text)
    if raw_lines[1::2] != corrected_lines[1::2]:
        raise MarkdownMappingError(
            "Nội dung chỉnh sửa đã thêm, xóa hoặc đổi dấu xuống dòng. "
            "Hãy giữ nguyên các dòng OCR và chỉ sửa nội dung trong từng dòng."
        )
    offset = 0
    for index in range(0, len(raw_lines), 2):
        for local_start, local_end, old_text, new_text in _text_diff(
            raw_lines[index], corrected_lines[index]
        ):
            start, end = _locate_replacement(
                markdown, raw_text, offset + local_start, offset + local_end, old_text
            )
            edits.append((start, end, old_text, new_text))
        offset += len(raw_lines[index])
        if index + 1 < len(raw_lines):
            offset += len(raw_lines[index + 1])

    return _render_changes(markdown, edits)


def _render_changes(
    markdown: str,
    edits: list[tuple[int, int, str, str]],
    literal_spans: set[tuple[int, int]] | None = None,
) -> MarkdownReview:
    literal_spans = literal_spans or set()
    ordered = sorted(edits, key=lambda edit: edit[0])
    for previous, current in zip(ordered, ordered[1:]):
        if previous[1] > current[0]:
            raise MarkdownMappingError("LLM corrections overlap in the OCR Markdown source.")

    llm_markdown = markdown
    changes: list[MarkdownChange] = []
    offset = 0
    for start, end, old_text, new_text in ordered:
        safe_text = new_text if (start, end) in literal_spans else _escape_markdown_text(new_text)
        final_start = start + offset
        changes.append(
            MarkdownChange(
                start=final_start,
                end=final_start + len(safe_text),
                before=old_text,
                after=new_text,
                before_start=start,
                before_end=end,
            )
        )
        offset += len(safe_text) - (end - start)

    for start, end, _, new_text in reversed(ordered):
        safe_text = new_text if (start, end) in literal_spans else _escape_markdown_text(new_text)
        llm_markdown = llm_markdown[:start] + safe_text + llm_markdown[end:]
    return MarkdownReview(markdown, llm_markdown, changes)


def build_markdown_review(
    raw_markdown: str,
    raw_text: str,
    corrected_text: str,
) -> MarkdownReview:
    """Apply text-only OCR fixes while retaining the original Markdown source structure."""
    return _apply_text_changes(raw_markdown, raw_text, corrected_text)


def apply_approved_text(
    raw_markdown: str,
    raw_text: str,
    approved_text: str,
) -> str:
    """Map a user-approved plain-text page back onto its immutable Markdown structure."""
    return build_manual_markdown_review(raw_markdown, raw_text, approved_text).llm_markdown


def build_manual_markdown_review(
    raw_markdown: str, raw_text: str, approved_text: str,
) -> MarkdownReview:
    """Allow human formula-body corrections while preserving Markdown structure."""
    original = _formula_matches(raw_text)
    approved = _formula_matches(approved_text)
    if len(original) != len(approved):
        raise MarkdownMappingError("Keep the existing formulas and their delimiters; edit only formula contents.")
    markdown_formulas = _formula_matches(raw_markdown)
    if original and [m.group() for m in original] != [m.group() for m in markdown_formulas]:
        raise MarkdownMappingError("OCR formulas do not align with Markdown; cannot safely map manual formula edits.")
    prose = approved_text
    formula_edits: list[tuple[int, int, str, str]] = []
    for old, new, md in reversed(list(zip(original, approved, markdown_formulas))):
        if old.group().startswith('$$') != new.group().startswith('$$'):
            raise MarkdownMappingError("Keep the formula's original inline/display delimiters.")
        if old.group() != new.group():
            formula_edits.append((md.start(), md.end(), old.group(), new.group()))
        prose = prose[:new.start()] + old.group() + prose[new.end():]
    mapped = _apply_text_changes(raw_markdown, raw_text, prose)
    edits = [(c.before_start, c.before_end, c.before, c.after) for c in mapped.llm_changes]
    return _render_changes(raw_markdown, edits + formula_edits,
                           {(start, end) for start, end, _, _ in formula_edits})


def build_human_markdown_review(before: str, approved: str) -> MarkdownReview:
    """Human-reviewed Markdown is authoritative; LLM restrictions do not apply."""
    changes = [
        MarkdownChange(j1, j2, before[i1:i2], approved[j1:j2], i1, i2)
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, before, approved, autojunk=False).get_opcodes()
        if tag != "equal"
    ]
    return MarkdownReview(before, approved, changes)


def shift_llm_changes(
    llm_changes: list[dict[str, int | str]],
    manual_changes: list[MarkdownChange],
) -> list[dict[str, int | str]]:
    """Move model highlight ranges after manual edits to the same Markdown source."""
    shifted: list[dict[str, int | str]] = []
    for model_change in llm_changes:
        start = int(model_change["start"])
        end = int(model_change["end"])
        delta = 0
        replaced_by_user = False
        for manual_change in manual_changes:
            if manual_change.before_start < end and manual_change.before_end > start:
                replaced_by_user = True
                break
            if manual_change.before_end <= start:
                delta += (manual_change.end - manual_change.start) - (
                    manual_change.before_end - manual_change.before_start
                )
        if not replaced_by_user:
            shifted.append({**model_change, "start": start + delta, "end": end + delta})
    return shifted
