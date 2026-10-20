# PaddleOCR-VL Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy OCR/preprocessing flow with direct PaddleOCR-VL processing for one image or PDF, saving per-page outputs under `data/raw/{document_name}/`.

**Architecture:** `backend/ocr_vl/engine.py` wraps and reuses `PaddleOCRVL`; `pipeline.py` validates an input file, derives a safe document name, stores native JSON/Markdown page outputs, and returns the output paths. A no-op correction hook follows inference so a later API call can be added without coupling the service to a web framework.

**Tech Stack:** Python, PaddleOCR-VL (`paddleocr[doc-parser]`), `pathlib`, JSON, argparse.

**Spec:** `docs/superpowers/specs/2026-10-20-paddleocr-vl-pipeline-design.md`

## Global Constraints

- Accept one local image or PDF path; supported image extensions remain `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`, and `.webp`.
- Do not require a caller-provided document ID; derive a safe folder name from the input filename stem.
- Write page JSON and Markdown files directly into `data/raw/{document_name}/` using stable `page_NNN` names.
- Preserve native PaddleOCR-VL outputs; do not apply the legacy confidence filter or reading-order heuristic.
- Do not add external grayscale, deskew, CLAHE, resize, or PDF rasterization stages.
- `correct_ocr_output(result)` remains a no-op and makes no LLM/API calls.
- Preserve unrelated dirty and untracked files, including the modified tracked preprocessing `.pyc`; remove obsolete source files without touching bytecode caches.
- Preserve the intent of the existing uncommitted `backend/ocr/pipeline.py` change: aggregate one page result for every page processed.
- Do not add or run tests unless requested.

## Review Focus

- Missing path or directory input: fail before model inference with a clear input error.
- Unsupported extension: list or identify the supported image/PDF formats in the error.
- Unsafe or colliding document folder name: reject without escaping `data/raw` or overwriting existing files.
- Multi-page PDF: keep source page order and emit one JSON/Markdown pair for every page.
- Model or output-write failure: do not report success or leave a partial final document directory.

---

### Task 1: Add the PaddleOCR-VL engine and document pipeline

**Files:**
- Create: `backend/ocr_vl/__init__.py`
- Create: `backend/ocr_vl/engine.py`
- Create: `backend/ocr_vl/pipeline.py`
- Create: `backend/ocr_vl/correction.py`
- Modify: `requirements.txt`
- Delete: `backend/ocr/engine.py`, `backend/ocr/pipeline.py`, `backend/ocr/postprocess.py`, `backend/ocr/reading_order.py`, `backend/ocr/schemas.py`, `backend/ocr/__init__.py`

**Interfaces:**
- `PaddleOCRVLEngine.__init__()` constructs one `PaddleOCRVL`; `predict(input_path: str | Path) -> list[Any]` reuses it and returns `list(self.pipeline.predict(input=str(input_path)))`.
- `correct_ocr_output(result: list[Any]) -> None` is a placeholder whose body is exactly `pass`.
- `process_document(input_path: str | Path, output_root: str | Path = "data/raw", engine: PaddleOCRVLEngine | None = None) -> dict[str, Any]` returns `{"document_name": str, "outputs": list[str]}`.

- [ ] Add the `backend/ocr_vl` package with an injectable engine, importing `PaddleOCRVL` lazily enough that importing the CLI/service does not download or initialize model weights.
- [ ] Replace `requirements.txt`'s preprocessing-only dependencies with `paddleocr[doc-parser]`; PaddlePaddle CPU/GPU installation remains environment-specific and is documented separately.
- [ ] Implement input validation, safe filename-stem normalization, output collision rejection, and temporary sibling-directory output. Do not copy or modify the source file.
- [ ] Call `engine.predict()` once with the original image/PDF. Invoke `correct_ocr_output(results)` without using its return value; persist the original PaddleOCR-VL results unchanged. Aggregate every PDF page in source order, preserving the page-per-result behavior intended by the current uncommitted pipeline edit.
- [ ] For each per-page result, use PaddleOCR-VL's native JSON and Markdown save methods in an isolated temporary page directory, rename the emitted `.json` and `.md` files to `page_NNN.json` and `page_NNN.md`, and preserve model-generated assets with a page-specific name. Rename the completed temporary document directory to `data/raw/{document_name}` only after all pages are written.
- [ ] Return the derived document name and final output paths. Add contextual errors for invalid input, model inference, and persistence failures; clean temporary output on failure.
- [ ] Review the five failure/page behaviors listed in Review Focus against the implementation; do not add or run a test suite.

### Task 2: Replace the CLI, remove preprocessing, and update contributor guidance

**Files:**
- Modify: `backend/run_ocr.py`
- Modify: `AGENTS.md`
- Delete: `backend/preprocess.py`
- Delete source files: `backend/preprocessing/__init__.py`, `backend/preprocessing/loader.py`, `backend/preprocessing/pdf_converter.py`, `backend/preprocessing/grayscale.py`, `backend/preprocessing/deskew.py`, `backend/preprocessing/enhancement.py`, `backend/preprocessing/resize.py`, `backend/preprocessing/pipeline.py`

**Interfaces:**
- CLI: `python -m backend.run_ocr <input_file> [--output-root data/raw]` delegates to `process_document()` and prints the document output directory.
- Contributor commands document direct image/PDF OCR and PaddleOCR-VL setup; there is no separate preprocessing command.

- [ ] Replace the old directory/output-JSON CLI arguments with one input-file argument and optional output root; delegate all processing to `backend.ocr_vl.pipeline.process_document`.
- [ ] Remove the standalone preprocessing command and its Python source modules. Leave all `__pycache__` contents untouched, including the modified tracked bytecode file.
- [ ] Update `AGENTS.md` to describe `backend/ocr_vl/`, the direct-input CLI, local output folder layout, dependency setup, and the current absence of an automated test suite.
- [ ] Review all active backend imports and documentation references to ensure no source still depends on `backend.ocr` or `backend.preprocessing`; leave `foldertree.txt` and other unrelated workspace files untouched.

## Completion Review

- Read the final diff and confirm only the plan's listed source/configuration/docs files changed, in addition to the pre-existing dirty files.
- Confirm output names and directory behavior match the approved spec.
- Do not run automated tests or model inference unless explicitly requested.
