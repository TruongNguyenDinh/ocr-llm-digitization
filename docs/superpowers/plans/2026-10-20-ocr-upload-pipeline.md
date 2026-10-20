# OCR Upload Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upload PDFs/images, run PaddleOCR-VL with page progress, and render its Markdown while exposing an inactive AI-correction control.

**Architecture:** FastAPI accepts multipart uploads and submits OCR work to a single-worker executor. An in-memory job registry exposes status and page Markdown by polling; OCR outputs remain in `data/raw/{document_name}/`. React owns upload/job state, previews the chosen source file, renders Markdown, and places the correction control in the left column.

**Tech Stack:** Python, FastAPI, Uvicorn, python-multipart, existing PaddleOCR-VL pipeline; React, TypeScript, Vite, react-markdown.

**Spec:** `docs/superpowers/specs/2026-10-20-ocr-upload-pipeline-design.md`

**Ruling:** Per the user's clarification, upload and correction controls belong to a dedicated Upload page; Dashboard retains its existing layout. This keeps document ingestion separate from the dashboard workspace.

## Global Constraints

- Keep OCR outputs under `data/raw/{document_name}/` and never overwrite an existing output folder.
- Process one PaddleOCR job at a time; job state is in memory and resets when the API restarts.
- The AI-correction button and model selector do not invoke Ollama.
- Do not add database persistence or change OCR preprocessing/finalization.
- Keep raw HTML disabled in Markdown rendering and constrain asset serving to the document output folder.
- Allow local Vite origins when the frontend uses `VITE_API_BASE_URL` for direct API calls; use the Vite proxy by default.

## Review Focus

- Unsupported extension or oversized upload: reject before scheduling OCR with a readable client error.
- Same-name documents: assign a unique output name without replacing old files.
- Unknown job ID: return a 404 response and show a recoverable UI error.
- OCR failure after partial progress: preserve completed raw pages and show failed state plus completed/total count.
- Markdown asset traversal or missing asset: never serve outside the document directory; show a broken asset without breaking page text.

---

### Task 1: Add OCR job API and queue

**Files:**
- Create: `backend/api/__init__.py`
- Create: `backend/api/jobs.py`
- Create: `backend/api/app.py`
- Modify: `requirements.txt`
- Modify: `backend/ocr_vl/pipeline.py`

**Interfaces:**
- `POST /api/ocr/jobs` accepts `UploadFile`, returns HTTP 202 with `{job_id: str}`.
- `GET /api/ocr/jobs/{job_id}` returns `{job_id, status, filename, document_name?, completed_pages, total_pages?, pages?, error?}`.
- Job statuses are `queued`, `running`, `completed`, `failed`; completed pages contain `{page_number, markdown}`.
- `GET /api/ocr/documents/{document_name}/{asset_path:path}` serves only files resolved within `data/raw/{document_name}`.

- [ ] Add FastAPI, Uvicorn, and python-multipart dependencies and define the job record/registry with a lock.
- [ ] Configure CORS for the local Vite development origins.
- [ ] Implement upload validation (PDF/image extensions and 100 MiB maximum), safe unique document naming, temporary source cleanup, and 202 response.
- [ ] Emit a `processing_started` callback from `process_document` with `completed=0` and known `total` before loading the model; keep existing `page_completed` callbacks unchanged.
- [ ] Submit `process_document(..., progress_callback=...)` to a one-worker `ThreadPoolExecutor`; callbacks update status/progress and page Markdown is read from the completed raw output directory.
- [ ] Implement polling and path-safe asset routes, including 404 for missing job/document/asset.
- [ ] Expose the app as `backend.api.app:app`; configure output root relative to repository root so launch directory does not redirect OCR output.

### Task 2: Connect frontend upload and progress state

**Files:**
- Create: `frontend/src/services/ocrApi.ts`
- Create: `frontend/src/components/UploadControl.tsx`
- Create: `frontend/src/components/CorrectionControls.tsx`
- Create: `frontend/src/pages/UploadPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.css`
- Modify: `frontend/vite.config.ts`
- Create: `frontend/.env.example`

**Interfaces:**
- `createOcrJob(file: File): Promise<string>` posts the file and returns the job ID.
- `getOcrJob(jobId: string): Promise<OcrJob>` retrieves the API response schema from Task 1.
- Upload page states: `idle`, `submitting`, `queued`, `running`, `completed`, and `failed`.

- [ ] Add a dedicated Upload page with a left-column file picker/button accepting supported PDF/image types; selecting a file starts upload. Keep Dashboard's existing search/chat/document layout unchanged.
- [ ] Poll active jobs once per second, stop polling on completion/failure/unmount, and display completed/total pages in the left column.
- [ ] Display API/network errors and allow retry with another file; clear stale job state on new upload.
- [ ] Show **AI correction** and a model selector in the Upload page's left column only after OCR completion; use `qwen3:8b` and `qwen3:4b` as UI choices without invoking a model.
- [ ] Configure Vite `/api` proxy to `http://127.0.0.1:8000` and document `VITE_API_BASE_URL` in `.env.example`.

### Task 3: Render source preview and OCR Markdown

**Files:**
- Modify: `frontend/src/components/DocumentViewer.tsx`
- Modify: `frontend/src/pages/UploadPage.tsx`
- Modify: `frontend/src/services/ocrApi.ts`
- Modify: `frontend/src/App.css`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Interfaces:**
- Viewer receives selected `File | null`, ordered `{page_number, markdown}` pages, job status, and `document_name`.
- Relative Markdown image links resolve through the Task 1 asset route; HTML remains disabled.

- [ ] Add `react-markdown` and render each OCR page as an ordered Markdown section in the digitized tab.
- [ ] Preview the selected image/PDF in the original tab using a temporary object URL and revoke it when replaced/unmounted.
- [ ] Render empty, in-progress, completed, and failed states while retaining original/digitized tabs.
- [ ] Ensure Markdown image URLs use the job's document name and safely encoded relative asset path.

### Task 4: Add local run instructions

**Files:**
- Modify: `README.md`

- [ ] Document backend installation and launch with `uvicorn backend.api.app:app --host 0.0.0.0 --port 8000`.
- [ ] Document frontend `.env` setup and `npm run dev`, and describe that OCR progress state is lost if the API process restarts.
