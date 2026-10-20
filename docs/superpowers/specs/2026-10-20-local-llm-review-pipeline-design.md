# Local LLM Review and Digitization Pipeline

## Goal

Extend the existing PaddleOCR-VL service with local OCR correction, document classification, metadata extraction, a review comparison payload, and post-review storage. Keep the backend framework-independent so a future web API can call the same service and relay progress events.

## Agreed requirements

- Use the local Ollama model `qwen3:8b`. Do not modify the separate Transformers/LoRA training and inference scripts.
- OCR an image or PDF with PaddleOCR-VL. Keep the original page JSON and Markdown in `data/raw/{document_name}/`.
- Emit a page-completion event after each OCR page, with `completed` and `total` values such as `1/3`. Do not start any LLM work until all OCR pages have completed.
- Send each page's OCR text as a separate correction request to Ollama. Preserve page boundaries and require correction to retain meaning and avoid adding or removing facts.
- After all page corrections complete, classify the document and extract sender, recipient, date/time when present, and document type from the corrected pages. Return structured data with a configurable label code/name registry; label code `1` is initially reserved for a letter.
- Keep OCR text, LLM-corrected text, and user-approved text distinct. A comparison service returns page-level differences for the final user review; LLM suggestions are never treated as user approval.
- Only after explicit review approval, save one Markdown file per page and the original document as one PDF. Preserve PDF inputs byte-for-byte; convert image inputs to a PDF, preserving the source image content and all frames/pages supported by the format.
- Store digitized files under `storage/digitization/{label}/{user_id}_{sequence}/page_NNN.md`; store the source under `storage/origin/{label}/{user_id}_{sequence}.pdf`.
- A framework-independent storage service accepts `user_id`, atomically allocates a per-user sequence, writes the final files, and records their paths and extracted metadata in a local SQLite database. Keep the repository boundary replaceable when a web deployment database is chosen.

## Architecture and flow

1. `backend/ocr_vl/pipeline.py` owns OCR inference and page output. Change the engine boundary to expose page results incrementally and accept an optional progress callback. Determine total pages before inference: images count as one, multi-frame images use their frame count, and PDFs use PDF page metadata. Emit progress only after that page's raw JSON/Markdown artifacts are successfully written.
2. A new `backend/llm/` package provides an Ollama client, correction/classification/extraction orchestration, typed response validation, and configurable labels. Use Ollama's local HTTP API and a configurable base URL/model name; no web framework dependency is introduced.
3. The document workflow runs in strict phases: all OCR pages; per-page correction calls; one document-level classification and metadata extraction call using page-numbered corrected text; then a review-ready result. If OCR fails, no LLM calls occur. If LLM processing fails, preserve raw OCR output and return a contextual processing error without writing final digitization files.
4. The comparison service produces a page-indexed payload containing raw OCR, corrected suggestion, and text diff. Persist a review-ready `review.json` beside raw page artifacts so a future web service can load it. The web client returns user-approved page text to a finalization service. The finalization service writes page Markdown and the original PDF, then commits metadata through a SQLite repository transaction. If persistence fails, clean newly staged files and do not mark the document finalized.
5. Use safe path components for label and user IDs. Allocate sequence values inside a SQLite transaction with a uniqueness constraint on `(user_id, sequence)`. Store document ID, user ID, sequence, label code/name, extracted fields, page count, source path, digitized page paths, origin PDF path, and review status. A temporary `local` user may be used by a CLI; service callers must pass a user ID explicitly.

## Interfaces

- `process_document(input_path, output_root="data/raw", engine=None, progress_callback=None)` returns the OCR document name, page count, raw output paths, and page texts needed for LLM processing.
- `LocalLLMWorkflow.process_pages(pages)` corrects each page separately, then returns corrected page texts, a document classification, and extracted metadata.
- `compare_pages(ocr_pages, corrected_pages)` returns stable page IDs and line/word differences suitable for a review UI.
- `finalize_review(review_id, user_id, approved_pages)` loads source and metadata from the persisted review record, stores reviewed pages and an origin PDF, and returns the stable document ID and paths.

Exact types may be refined during implementation planning, but page IDs, label code/name, user ID, sequence, and storage paths must remain explicit at module boundaries.

## Failure handling and data integrity

- Validate Ollama availability and model configuration before making a document's LLM calls; report connection, timeout, and invalid structured-output errors with the page/document context.
- Keep every LLM response as a suggestion and validate required fields before returning it to review.
- Do not overwrite existing raw or finalized document directories. Use staging paths and atomic renames where possible.
- Never report a page complete before its raw artifacts are durable. Never report a document finalized before both files and metadata are committed.
- Keep original OCR artifacts immutable; final Markdown is derived only from user-approved content.

## Scope boundaries

This change adds no HTTP routes, authentication, frontend, remote LLM calls, automatic user approval, or changes to LoRA training. SQLite is a local persistence implementation behind a repository interface, not a commitment to the future production database.

## Validation approach

Keep OCR and Ollama clients injectable so their boundaries can be isolated. For this implementation, use syntax checks and focused manual validation only; do not add or run automated tests unless explicitly requested. A manual smoke run can use the installed Ollama `qwen3:8b` model and an existing image/PDF when requested.
