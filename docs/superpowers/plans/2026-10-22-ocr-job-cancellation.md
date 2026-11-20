# OCR Job Cancellation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop PaddleOCR-VL and its child processes when a user presses **Dừng OCR** or reloads/closes the Upload page, releasing VRAM for local LLM use.

**Architecture:** Move one OCR job at a time into a dedicated Python subprocess started in its own POSIX process group. The API supervises the process, forwards framed progress events to its in-memory job store, and can terminate the complete process group. The frontend calls the cancellation endpoint from both the stop button and a `pagehide` handler.

**Tech Stack:** Python 3.10+, FastAPI, `subprocess.Popen`, POSIX process groups in WSL/Linux; React, TypeScript, Fetch API.

**Spec:** `docs/superpowers/specs/2026-10-22-ocr-job-cancellation-design.md`

## Global Constraints

- Keep one OCR job active at a time.
- Use `queued`, `running`, `completed`, `failed`, and `cancelled` as backend job statuses.
- Do not change OCR text extraction, LLM correction, approval, or finalization behavior.
- On cancellation, delete only the job's temporary source and its incomplete output directory after validating both paths.
- Keep completed OCR output; a later cancel request must not remove it.
- Keep the job state process-local as in the current app.
- The process-group implementation targets the repository's POSIX/WSL runtime.
- The repository has no automated test suite. Do not add or run tests under this plan; run the listed syntax/build checks and report that GPU lifecycle verification requires a real OCR job.

## Review Focus

- Cancel before the executor starts a queued job: worker must not launch; source and name reservation are removed.
- Cancel in the window between process launch and registry insertion: cancellation request must be remembered and applied as soon as the process is registered.
- Cancel during Paddle generation: terminate the whole process group, not the API or only its parent worker.
- Worker exits at the same time cancellation arrives: the first terminal state wins; completed output is never deleted.
- Reload/close request is interrupted by browser/network shutdown: UI may lose confirmation, but API cancellation remains authoritative and cleanup is idempotent.

---

### Task 1: Add a standalone OCR worker protocol

**Files:**
- Create: `backend/ocr_vl/worker.py`
- Review: `backend/ocr_vl/engine.py`
- Review: `backend/ocr_vl/pipeline.py`

**Interfaces:**
- Worker command: `python -m backend.ocr_vl.worker --source <path> --output-root <path>`.
- Worker stdout event frame: `OCR_EVENT:` followed by one JSON object. Events are the existing `processing_started` and `page_completed` event payloads, plus a terminal `failed` event containing a readable `error` string.
- `PaddleOCRVLEngine.close() -> None` calls the underlying PaddleOCR-VL `close()` when available.
- `process_document(...)` closes an engine that exposes `close()` on both success and failure.

- [ ] Implement the worker CLI to call `process_document`, serialize progress frames with UTF-8 and flush each frame, emit a failure frame on exceptions, and exit with code 0 only on success.
- [ ] Keep Paddle and other worker diagnostics separate from machine-readable protocol frames; the API must be able to ignore non-frame output safely.
- [ ] Review the existing `PaddleOCRVLEngine.close()` and `process_document` `finally` cleanup hooks; retain them and adjust only if the worker integration exposes a cleanup gap.
- [ ] Run `python -m py_compile backend/ocr_vl/worker.py backend/ocr_vl/engine.py backend/ocr_vl/pipeline.py` and inspect the worker's sample event framing without running OCR.

### Task 2: Supervise and cancel worker processes in the API

**Files:**
- Modify: `backend/api/jobs.py`
- Modify: `backend/api/app.py`

**Interfaces:**
- Add `cancelled` to `JobStatus` and `OCRJob` response state.
- Add `POST /api/ocr/jobs/{job_id}/cancel -> OCRJob response`; unknown jobs return 404; terminal jobs return their existing terminal record.
- Launch workers with `subprocess.Popen(..., start_new_session=True, stdout=PIPE, stderr=STDOUT, text=True, encoding="utf-8", bufsize=1)` from `REPOSITORY_ROOT`.
- Track queued `Future` objects and active `Popen` objects by job ID under a lock; track cancellation requests that race worker startup.
- A shared `_terminate_job_process(process, grace_seconds)` helper sends `SIGTERM` to `os.killpg(process.pid, ...)`, waits for the grace period, then sends `SIGKILL` to the process group if needed.

- [ ] Replace direct in-thread `process_document` execution with a supervisor that launches the worker subprocess and consumes framed progress lines, updating the existing job store.
- [ ] Implement cancellation for queued jobs with `Future.cancel()` and for running jobs with process-group termination; ensure a cancellation request received before `Popen` registration is applied after registration.
- [ ] Make terminal-state transitions race-safe so cancellation cannot overwrite `completed`/`failed`, and a worker exit caused by cancellation cannot overwrite `cancelled` with `failed`.
- [ ] Make source cleanup, process/future registry removal, and document-name reservation release idempotent across completion, failure, cancellation, and queued cancellation.
- [ ] On FastAPI graceful shutdown, terminate all registered OCR process groups before the app exits.
- [ ] For cancelled jobs, resolve the output path and delete it only if it is a direct child of `OUTPUT_ROOT` and matches that job's reserved document name.
- [ ] Run `python -m py_compile backend/api/jobs.py backend/api/app.py backend/ocr_vl/worker.py` and inspect API route schemas without starting OCR.

### Task 3: Add stop control and page-unload cancellation

**Files:**
- Modify: `frontend/src/services/ocrApi.ts`
- Modify: `frontend/src/components/UploadControl.tsx`
- Modify: `frontend/src/pages/UploadPage.tsx`

**Interfaces:**
- Add `cancelled` to `OcrJobStatus` and `UploadStatus`.
- Add `cancelOcrJob(jobId: string, keepalive?: boolean): Promise<OcrJob>` to call `POST /api/ocr/jobs/{jobId}/cancel`.
- Add an `onCancel` callback and `isCancelling` prop to `UploadControl`.

- [ ] Render a **Dừng OCR** button for `queued` and `running`; disable it while the API cancellation request is pending.
- [ ] Show **“Vui lòng giữ cửa sổ trong quá trình xử lý. Không chuyển sang trang khác của web.”** while the job is queued or running.
- [ ] Handle button cancellation by calling `cancelOcrJob`, applying the returned terminal record, stopping polling, and showing the cancelled state.
- [ ] Cancel an active job when `UploadPage` unmounts due to internal route navigation; register `pagehide` and send the same cancellation request with `keepalive: true` for reload/tab close. Make both requests idempotent and remove the listener once the job becomes terminal or the component unmounts.
- [ ] Stop polling for `completed`, `failed`, and `cancelled`; retain the existing transient polling retry behavior and ensure cancellation errors do not masquerade as OCR failure.
- [ ] Run `npm run build` and inspect the Upload page states for queued, running, cancelling, cancelled, completed, and failed.

### Task 4: Verify process and VRAM lifecycle

**Files:**
- No additional files unless a defect is found in Tasks 1–3.

**Interfaces:**
- Use the existing job polling endpoint and `nvidia-smi` to observe job state, process IDs, GPU process list, and VRAM usage.

- [ ] With a small multi-page document, start OCR and stop it from the button; confirm API returns `cancelled`, worker and descendants exit, temporary/input and partial output files are removed, and VRAM returns near its pre-job level.
- [ ] Start another OCR job and reload the Upload page; confirm `pagehide` requests cancellation and the same process/file/VRAM cleanup occurs.
- [ ] Cancel a queued job and confirm no worker process starts.
- [ ] Complete a job normally and confirm page outputs remain, status is `completed`, and calling cancel afterward does not alter or delete them.
- [ ] Report each manual check with observed job status, process exit, and before/after VRAM; do not claim lifecycle success unless these observations confirm it.
