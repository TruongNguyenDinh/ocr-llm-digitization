from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Iterable

from .schemas import CorrectedPage, PageText


@dataclass(frozen=True)
class PageComparison:
    page_id: str
    ocr_text: str
    suggested_text: str
    operations: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def compare_pages(
    ocr_pages: Iterable[PageText | dict[str, object]],
    corrected_pages: Iterable[CorrectedPage],
) -> list[PageComparison]:
    raw_pages = [
        page
        if isinstance(page, PageText)
        else PageText(str(page["page_id"]), str(page["text"]))
        for page in ocr_pages
    ]
    suggestions = list(corrected_pages)
    if [page.page_id for page in raw_pages] != [page.page_id for page in suggestions]:
        raise ValueError("OCR and corrected pages must have matching page IDs/order")

    comparisons: list[PageComparison] = []
    for raw, corrected in zip(raw_pages, suggestions):
        old_lines = raw.text.splitlines()
        new_lines = corrected.corrected_text.splitlines()
        matcher = SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
        operations = [
            {
                "type": tag,
                "old_start": old_start,
                "old_end": old_end,
                "new_start": new_start,
                "new_end": new_end,
                "old_lines": old_lines[old_start:old_end],
                "new_lines": new_lines[new_start:new_end],
            }
            for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes()
        ]
        comparisons.append(
            PageComparison(
                page_id=raw.page_id,
                ocr_text=raw.text,
                suggested_text=corrected.corrected_text,
                operations=operations,
            )
        )
    return comparisons
