from pathlib import Path
from typing import Any

from backend.llm.comparison import compare_pages
from backend.llm.review_store import save_review_draft
from backend.llm.schemas import ReviewDraft
from backend.llm.workflow import LocalLLMWorkflow
from backend.ocr_vl.pipeline import OCREngine, ProgressCallback, process_document


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
