# PaddleOCR-VL Backend Pipeline Design

## Goal and agreed constraints

Replace the legacy PaddleOCR recognition path with PaddleOCR-VL. The backend must accept a single image or PDF and expose a framework-independent service that a future web API can call. Save model output files directly in `data/raw/{document_name}/`, where `document_name` is derived from the input filename; callers do not supply an ID. OCR correction by an LLM API is a future step and remains a no-op (`pass`) in this change. No LLM or web framework integration is included.

## Current state

`backend/ocr/engine.py` wraps `PaddleOCR` and returns detector/recognizer output. `postprocess.py`, `reading_order.py`, and `schemas.py` assume `rec_texts`, `rec_scores`, and `rec_polys`. `pipeline.py` accepts a directory of preprocessed PNG pages, not an original file. The separate preprocessing package rasterizes PDFs and applies grayscale, deskew, CLAHE, and resizing. Those transformations are not appropriate as mandatory inputs to the new layout-aware model. `backend/LoRA/` is a separate OCR-correction training/inference area and is outside this migration.

## Proposed components and flow

1. `backend/ocr_vl/pipeline.py` exposes `process_document(input_path, output_root="data/raw")`. It validates that the input exists and has a supported image/PDF extension. Derive a safe folder name from the input stem; do not accept a caller-provided ID or copy the source file.
2. `backend/ocr_vl/engine.py` owns construction and reuse of one `PaddleOCRVL` instance. It accepts the input path and returns native per-page prediction results. Keep the engine injectable so service/API callers can reuse the loaded model and substitute a fake engine for isolated validation.
3. After inference, invoke `correct_ocr_output(result)` as the future correction hook. Its current body is only `pass`; do not call an LLM or external API in this change, and save the PaddleOCR-VL output unchanged.
4. Persist each page's structured JSON and Markdown output directly in `data/raw/{document_name}/`, with stable page numbering (`page_001`, `page_002`, …) and any model-generated assets alongside those files. Return the derived document name and output paths so a future web route can form a response without depending on PaddleOCR internals.
5. `backend/run_ocr.py` becomes a thin CLI caller of the same service with only an input file argument. It must not be a separate OCR implementation.

PaddleOCR-VL's documented `predict` flow accepts image and PDF paths and yields a result per page. Its built-in document orientation and unwarping options should be the first choice for those corrections. Do not force grayscale, CLAHE, deskew, resizing, or a PDF-to-image intermediate pipeline. Retain only file validation; add optional external preprocessing later only if representative-document evaluation shows a measurable need.

## Output and failure behavior

Create the document output directory after validating the input. Derive `document_name` from the source filename stem, normalize it to a safe single path segment, and fail without overwriting if `data/raw/{document_name}` already exists. Preserve PaddleOCR-VL structured JSON and Markdown rather than rebuilding old `OCRBlock` records or applying the old 0.50 confidence filter and column-order heuristic. Preserve page boundaries. Raise clear input errors for missing, unsupported, or unreadable files, and contextualize inference/output failures with the input path. Do not report success when only part of the outputs was written; write each artifact through a temporary file and rename it after a successful write where practical. The correction hook is a no-op and must not alter the OCR result.

Expected layout:

```text
data/raw/{document_name}/
  page_001.json
  page_001.md
  page_002.json
  page_002.md
```

The future API stores uploads and calls the service with an input path; the service derives and returns the document name. This migration does not add an HTTP framework, LLM integration, correction API call, queue, or database.

## Files in scope

- Replace the legacy OCR engine and pipeline with `backend/ocr_vl/engine.py` and `backend/ocr_vl/pipeline.py`; remove the obsolete `backend/ocr/` package and its PaddleOCR-only normalization, reading-order, schema, and engine files.
- Add `correct_ocr_output(result)` as a no-op hook after OCR for future LLM API integration; do not add LLM dependencies or network calls.
- Replace `backend/run_ocr.py` with a thin service CLI.
- Remove `backend/preprocess.py` and `backend/preprocessing/`; the direct-input model pipeline supersedes their preprocessing CLI and intermediate images.
- Update `requirements.txt` and the repository's `AGENTS.md` commands/structure to describe PaddleOCR-VL and direct image/PDF processing.
- Leave `backend/LoRA/`, datasets, checkpoints, and unrelated local changes untouched.

## Validation and risks

The repository currently has no automated test suite. Validate the OCR service boundary with a fake engine and temporary image/PDF fixtures if tests are added in a later test-focused change; do not require model downloads for basic validation. A real smoke run requires PaddleOCR-VL dependencies and a compatible device/runtime and should use a small representative image and PDF. The PaddleOCR-VL result shape and asset-saving behavior must be confirmed against the installed version before finalizing serialization. Existing uncommitted changes in `backend/ocr/pipeline.py` must be preserved while replacing that file, and unrelated dirty/untracked files must not be swept into the change.

## Reference

PaddleOCR-VL image/PDF inference and per-page result export: [PaddlePaddle PaddleOCR-VL documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md).
