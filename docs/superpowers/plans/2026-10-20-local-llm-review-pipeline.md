# Local LLM Review and Digitization Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend PaddleOCR-VL into a page-aware OCR correction, classification, review, and approved-document storage workflow using local Ollama.

**Architecture:** OCR emits durable page artifacts and progress events before any LLM call starts. An Ollama workflow corrects each page separately, then classifies/extracts document metadata; a comparison service persists review data. Finalization stores user-approved Markdown pages, the original document as PDF, and path/metadata records in SQLite.

**Tech Stack:** Python 3.10+, PaddleOCR-VL, Ollama HTTP API via `urllib`, `pypdf`, Pillow, SQLite, standard-library `difflib`.

**Spec:** `docs/superpowers/specs/2026-10-20-local-llm-review-pipeline-design.md`

## Global Constraints

- Use Ollama model `qwen3:8b`; do not alter `backend/LoRA/` or its Transformers workflows.
- Do not call Ollama until all OCR pages have completed and their raw JSON/Markdown artifacts are written.
- Correct one page per LLM request; keep raw OCR, corrected suggestions, and user-approved text separate.
- Do not finalize files before an explicit user review decision.
- Save approved page Markdown under `storage/digitization/{label}/{user_id}_{sequence}/` and the source PDF under `storage/origin/{label}/`.
- Keep all services framework-independent; do not add web routes or authentication.
- Do not add or run automated tests unless explicitly requested; perform syntax and focused manual validation only.

## Review Focus

- A one-page image reports `1/1`; a multi-page PDF reports each successful page through `n/n`, with no LLM call before the last OCR page.
- A failed Ollama call leaves raw OCR artifacts available and creates no finalized digitization or origin files.
- Correction prompts contain exactly one page; classification/extraction receives corrected page text with page identifiers and validates structured fields.
- Comparison preserves page boundaries and never marks model text as user-approved.
- Concurrent finalizations for one user receive unique sequences; path or database failure removes staged/final files and does not mark the record complete.
- A PDF source is preserved byte-for-byte; supported image sources become one multi-page-capable PDF.

---

### Task 1: Add incremental OCR page output and progress events

**Files:**
- Modify: `backend/ocr_vl/engine.py`
- Modify: `backend/ocr_vl/pipeline.py`
- Modify: `requirements.txt`

**Interfaces:**
- Engine `predict(input_path) -> Iterable[Any]` yields PaddleOCR-VL page results in source order.
- Service `process_document(input_path, output_root="data/raw", engine=None, progress_callback=None) -> dict[str, Any]` includes page count, raw page paths, and extracted page text.
- Progress callback receives a serializable event with document name, completed page count, total page count, and page number.

- [ ] Add `pypdf` and direct `Pillow` dependencies for PDF page counting and conversion of raster inputs during finalization.
- [ ] Pre-count PDF pages with `pypdf` and image frames with Pillow before inference; use one page for single-frame images.
- [ ] Return the native PaddleOCR-VL iterator instead of eagerly converting it to a list.
- [ ] Write each page's JSON, Markdown, and assets into a page-specific staging directory under `data/raw/{document_name}/`; atomically move that page's files into place before emitting its `completed/total` callback.
- [ ] Extract correctable page text from the native Markdown while protecting image tags and asset references; keep original JSON/Markdown unchanged and return pages in source order.
- [ ] Reject an output collision before inference and fail with a contextual error if the number of returned page results differs from the pre-count.
- [ ] Perform a syntax check and manual one-image OCR smoke check; inspect that one page emits `1/1` after its artifacts appear.

### Task 2: Implement Ollama client and local LLM document workflow

**Files:**
- Create: `backend/llm/__init__.py`
- Create: `backend/llm/ollama_client.py`
- Create: `backend/llm/schemas.py`
- Create: `backend/llm/labels.json`
- Create: `backend/llm/workflow.py`
- Create: `backend/llm/prompts.py`

**Interfaces:**
- `OllamaClient.chat(messages, response_format=None) -> str` uses configurable `OLLAMA_BASE_URL` and `OLLAMA_MODEL` defaults (`http://localhost:11434`, `qwen3:8b`).
- `LocalLLMWorkflow.process_pages(pages) -> ReviewDraft` accepts ordered page IDs/text and returns corrected page text, label code/name, sender, recipient, date/time, and document type.

- [ ] Implement the Ollama `/api/chat` client with timeout, connection errors, and JSON-format requests using only the Python standard library.
- [ ] Define typed dataclasses and strict JSON parsing for correction and classification/extraction responses; reject missing/invalid required fields while allowing absent extracted values to be `null`.
- [ ] Add Vietnamese prompts that correct only OCR errors without adding/omitting facts; call once for each page, sequentially, preserving stable page IDs.
- [ ] Add a configurable label registry with code `1` for letter and an explicit unclassified fallback; instruct the model to select a registered code/name pair.
- [ ] After all per-page correction calls finish, make one document-level classification/extraction call with corrected text labeled by page number.
- [ ] Ensure any LLM error includes document/page context and leaves the completed raw OCR outputs untouched.
- [ ] Perform syntax checks and a manual request to the configured local Ollama model when available; do not add automated tests.

### Task 3: Add comparison and persisted review-ready records

**Files:**
- Create: `backend/llm/comparison.py`
- Create: `backend/llm/review_store.py`
- Modify: `backend/llm/workflow.py`

**Interfaces:**
- `compare_pages(ocr_pages, corrected_pages) -> list[PageComparison]` returns stable page IDs, OCR text, suggested text, and line-level diff operations.
- `save_review_draft(raw_document_dir, draft, comparisons) -> Path` writes `review.json` in the raw document folder.
- `load_review_draft(review_id) -> ReviewDraft` loads the persisted source path, page data, and extracted metadata for finalization.

- [ ] Use `difflib.SequenceMatcher` to emit page-local equal/insert/delete/replace operations with line text and indexes.
- [ ] Persist raw text, LLM suggestions, diff operations, label, extracted fields, source path, page count, and `pending_review` status in an atomically written `data/raw/{document_name}/review.json`.
- [ ] Assign a stable review ID and prevent a second draft from overwriting an existing raw document or review record.
- [ ] Keep review state separate from final-approved page content; never auto-approve a suggestion.
- [ ] Perform syntax checks and inspect a manually generated review JSON for page IDs and readable diffs.

### Task 4: Add SQLite metadata repository and post-review storage service

**Files:**
- Create: `backend/storage/__init__.py`
- Create: `backend/storage/repository.py`
- Create: `backend/storage/service.py`

**Interfaces:**
- `finalize_review(review_id, user_id, approved_pages, storage_root="storage", repository=None) -> dict[str, Any]` requires one approved text for every page and returns document ID, label, sequence, and saved paths.
- `get_digitized_document(document_id, storage_root="storage", repository=None)` returns the persisted metadata and file paths for a future web caller.
- SQLite repository initializes `storage/metadata.sqlite3` and stores document metadata, page paths, origin path, and status.

- [ ] Create SQLite schema with document ID, user ID, per-user sequence, label code/name, sender, recipient, date/time, document type, page count, source path, digitized paths, origin PDF path, and review status; enforce unique `(user_id, sequence)`.
- [ ] Allocate sequence within `BEGIN IMMEDIATE` and sanitize `user_id` and label values before using them as path components.
- [ ] Stage per-page `page_NNN.md` files and `{user_id}_{sequence}.pdf` before moving into the agreed storage directories; copy PDF inputs unchanged and convert raster inputs with Pillow, preserving supported frames.
- [ ] Commit files and metadata with rollback cleanup: never overwrite an existing destination, and remove staged or newly moved files if the database commit fails.
- [ ] Require explicit approval for every page and update status to `finalized` only after file writes and the metadata transaction succeed.
- [ ] Perform syntax checks and a manual finalization using a disposable SQLite file and sample input; inspect both stored content and DB paths.

### Task 5: Orchestrate the complete workflow for CLI and future web callers

**Files:**
- Create: `backend/document_workflow.py`
- Create: `backend/run_digitization.py`
- Modify: `AGENTS.md`

**Interfaces:**
- `prepare_document(input_path, progress_callback=None) -> ReviewDraft` sequences OCR, per-page corrections, classification/extraction, comparison, and review persistence.
- CLI `python -m backend.run_digitization <input_file>` prepares review data and prints the review JSON path; it must not finalize without user-approved page text.

- [ ] Wire services in strict order so all OCR page callbacks complete before constructing/calling the LLM workflow.
- [ ] Return a framework-neutral progress event contract that a future API can serialize unchanged.
- [ ] Add a CLI with progress output (`completed/total`) and a review-ready result path. Keep `user_id` as a required finalization-service input supplied by a future web caller.
- [ ] Update `AGENTS.md` with Ollama setup/model requirements, full command flow, review confirmation requirement, storage/SQLite paths, and the lack of web routes.
- [ ] Run static syntax checks and a focused manual end-to-end run on an existing image if Ollama `qwen3:8b` is available; inspect progress, review JSON, and verify final storage is untouched before review.

## Completion Review

- Read the final diff and confirm the existing OCR CLI remains usable and no files under `backend/LoRA/` were modified.
- Confirm the processing phases are ordered OCR-all-pages, LLM-correct-each-page, classify/extract-on-corrected-document, review, then explicit finalization.
- Confirm all raw and final outputs retain page boundaries, and the origin is always one PDF.
- Do not run automated tests unless explicitly requested.
