from dataclasses import replace
from pathlib import Path
import re
from typing import Any

from backend.llm.comparison import compare_pages
from backend.llm.review_store import save_review_draft
from backend.llm.markdown_review import MarkdownMappingError, build_markdown_review
from backend.llm.schemas import PageText, ReviewDraft, ReviewMarkdownPage
from backend.llm.workflow import LocalLLMWorkflow
from backend.ocr_vl.pipeline import OCREngine, ProgressCallback, process_document


def prepare_review_from_output(
    document_name: str,
    *,
    provider: str = "qwen",
    output_root: str | Path = "data/raw",
) -> ReviewDraft:
    """Run LLM review for an OCR-completed document already on disk."""
    if not re.fullmatch(r"[\w.-]{1,120}", document_name, flags=re.UNICODE):
        raise ValueError("Invalid document name")
    root = Path(output_root).resolve()
    document_dir = (root / document_name).resolve()
    if document_dir.parent != root or not document_dir.is_dir():
        raise FileNotFoundError(f"Completed OCR document not found: {document_name}")

    source_files = list(document_dir.glob("_source.*"))
    if len(source_files) != 1 or not source_files[0].is_file():
        raise FileNotFoundError("Original uploaded source is unavailable for final storage.")
    text_files = sorted(document_dir.glob("page_*.txt"))
    markdown_files = sorted(document_dir.glob("page_*.md"))
    json_files = sorted(document_dir.glob("page_*.json"))
    if not text_files or len(text_files) != len(markdown_files) or len(text_files) != len(json_files):
        raise ValueError("OCR output is incomplete; expected matching TXT, Markdown, and JSON pages.")
    page_ids = [path.stem for path in text_files]
    expected_ids = [f"page_{index:03d}" for index in range(1, len(text_files) + 1)]
    if (
        page_ids != expected_ids
        or [path.stem for path in markdown_files] != expected_ids
        or [path.stem for path in json_files] != expected_ids
    ):
        raise ValueError("OCR page outputs are missing or out of order.")

    raw_pages = [
        PageText(page_id=path.stem, text=path.read_text(encoding="utf-8"))
        for path in text_files
    ]
    workflow = LocalLLMWorkflow(provider=provider)
    draft = workflow.process_pages(
        raw_pages,
        document_name=document_name,
        source_path=str(source_files[0].resolve()),
        raw_document_dir=str(document_dir),
    )
    markdown_pages: list[ReviewMarkdownPage] = []
    try:
        for raw_page, corrected_page, markdown_path in zip(
            raw_pages, draft.pages, markdown_files, strict=True
        ):
            mapped = build_markdown_review(
                markdown_path.read_text(encoding="utf-8"),
                raw_page.text,
                corrected_page.corrected_text,
            )
            markdown_pages.append(
                ReviewMarkdownPage(
                    page_id=raw_page.page_id,
                    ocr_markdown=mapped.ocr_markdown,
                    llm_markdown=mapped.llm_markdown,
                    llm_changes=[change.to_dict() for change in mapped.llm_changes],
                )
            )
    except MarkdownMappingError as exc:
        raise ValueError(f"Could not preserve OCR Markdown structure: {exc}") from exc

    draft = replace(draft, markdown_pages=markdown_pages)
    comparisons = compare_pages(raw_pages, draft.pages)
    save_review_draft(document_dir, draft, comparisons)
    return draft


def prepare_document(
    input_path: str | Path,
    progress_callback: ProgressCallback | None = None,
    *,
    output_root: str | Path = "data/raw",
    ocr_engine: OCREngine | None = None,
    llm_workflow: LocalLLMWorkflow | None = None,
) -> ReviewDraft:
    """Run OCR to completion, then prepare an LLM suggestion for human review."""
    ocr_result = process_document(
        input_path,
        output_root=output_root,
        engine=ocr_engine,
        progress_callback=progress_callback,
    )
    pages = ocr_result["pages"]
    workflow = llm_workflow or LocalLLMWorkflow()
    draft = workflow.process_pages(
        pages,
        document_name=ocr_result["document_name"],
        source_path=str(Path(input_path).expanduser().resolve()),
        raw_document_dir=ocr_result["output_dir"],
    )
    comparisons = compare_pages(pages, draft.pages)
    save_review_draft(ocr_result["output_dir"], draft, comparisons)
    return draft
