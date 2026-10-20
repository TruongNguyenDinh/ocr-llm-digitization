# Repository Guidelines

## Project Structure

`backend/ocr_vl/` wraps PaddleOCR-VL and writes page JSON, Markdown, and plain-text files to `data/raw/{document_name}/`. The LLM receives only the ordered plain text from each page's JSON blocks. `backend/llm/` contains the Ollama client, per-page OCR correction, document classification/extraction, and review comparison. `backend/storage/` handles approved files and SQLite metadata. `backend/LoRA/` is a separate training/evaluation area and should not be changed for the Ollama workflow.

## Setup and Commands

Use Python 3.10+ in a virtual environment. Install PaddlePaddle for the machine's CPU/GPU, then install project dependencies:

```bash
python -m pip install -r requirements.txt
ollama pull qwen3:8b
```

Keep Ollama running locally. Override its settings with `OLLAMA_BASE_URL` and `OLLAMA_MODEL` if needed. Run OCR only with:

```bash
python -m backend.run_ocr path/to/document.pdf
```

Prepare OCR and LLM suggestions for review with:

```bash
python -m backend.run_digitization path/to/document.pdf
```

The command reports OCR progress as pages finish and writes `review.json` beside the raw page outputs. It does not approve suggestions or finalize files.

## Review and Storage

Keep OCR text, LLM suggestions, and user-approved page text separate. Finalize only after receiving approved text for every page through `backend.storage.finalize_review(review_id, user_id, approved_pages)`. Approved pages are stored under `storage/digitization/{label}/{user_id}_{sequence}/`; the source is stored as one PDF under `storage/origin/{label}/`. SQLite metadata defaults to `storage/metadata.sqlite3`. Image sources are converted to PDF during finalization; PDF sources are copied unchanged.

## Style and Changes

Use four spaces for Python indentation, `snake_case` for modules/functions, and type annotations at service boundaries. Keep services framework-independent so future web routes can reuse them. Preserve stable page IDs such as `page_001`. Do not commit source documents, generated OCR/review output, model weights, credentials, or virtual environments. No web routes or automated test suite are configured.
