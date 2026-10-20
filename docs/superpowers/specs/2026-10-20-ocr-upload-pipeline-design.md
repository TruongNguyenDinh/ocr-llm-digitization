# OCR Upload and Review UI Design

## Goal

Let a user upload an image or PDF from the dashboard, follow PaddleOCR-VL progress page by page, and read the resulting Markdown. Keep LLM correction as a selectable but inactive next step.

## User flow

1. The left column provides a file picker for supported image types and PDF. Selecting a file starts an OCR job.
2. The left column shows queued/running state and completed pages out of total pages. Failures show a readable error and allow another upload.
3. When OCR completes, the right document area renders each page's Markdown in order. The original tab previews the selected local file when the browser supports it.
4. The left column reveals an **AI correction** button and model selector after OCR completes. The control is presentational only; it does not call Ollama.

## Backend API

Add a FastAPI app, runnable with Uvicorn. `POST /api/ocr/jobs` accepts one multipart image/PDF and returns a job ID. OCR runs in a single-worker executor to avoid concurrent Paddle jobs competing for GPU memory. `GET /api/ocr/jobs/{job_id}` returns `queued`, `running`, `completed`, or `failed`, plus `completed_pages`, `total_pages`, and, on success, the ordered page Markdown and document name. `process_document` remains the OCR implementation and its page callback updates job progress. Serve OCR-exported assets through a path-safe document asset endpoint so Markdown images can render.

Job state stays in memory for this initial version; restarting the API loses job status. Uploaded source files use temporary storage and are removed after OCR. Durable model outputs remain under `data/raw/{document_name}/`. Generate a unique safe document name when an output directory already exists; never overwrite prior OCR results. Validate file type and size before starting a job.

## Frontend structure and states

Keep upload and AI-correction controls in the left column, above the existing chat panel. The file picker has empty, selected, uploading/queued, running, completed, and failed states. Poll the job endpoint while active. Put the Markdown page viewer in the existing right-side document panel and retain its original/digitized tabs. The correction model choices initially include the configured local models; selecting one changes UI state only.

Configure the API base through `VITE_API_BASE_URL` and proxy `/api` to the local FastAPI server during Vite development. Use a Markdown renderer with raw HTML disabled, and resolve relative exported asset URLs through the backend asset endpoint.

## Boundaries

This work adds upload/OCR transport and presentation only. It does not invoke Ollama, alter OCR preprocessing, add database persistence, or finalize digitized/origin documents. A missing or unknown job ID returns a clear API error. The UI must distinguish an empty document state from active progress and OCR failure.
