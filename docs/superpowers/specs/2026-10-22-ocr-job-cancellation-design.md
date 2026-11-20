# OCR Job Cancellation Design

## Goal

Let users stop an active PaddleOCR-VL job from the Upload page, and automatically stop that job when the page is reloaded or closed. Cancellation must end the OCR process tree so Paddle's CUDA context releases its VRAM for local LLM use.

## Evidence and current behavior

The upload API runs `process_document` in a `ThreadPoolExecutor`. PaddleOCR-VL creates a separate Python process that can remain alive after the job reports `completed`; a completed five-page job was observed with its worker still holding about 7.7 GiB of VRAM. A Python thread cannot safely terminate that worker and any Paddle descendants. The browser currently has no cancellation route or control.

## Architecture

Run each OCR job in a dedicated subprocess launched in its own process group. The API remains responsible for job state and progress. The worker emits framed progress and terminal events over stdout; the API ignores ordinary Paddle log lines and applies only messages with the worker protocol prefix. On POSIX/WSL, cancellation sends `SIGTERM` to the job process group, waits briefly, then sends `SIGKILL` if any process remains. This contains the worker and its descendants without terminating the API.

Keep the single-job execution limit. Track the queued future and launched subprocess by job ID under a lock so cancellation handles both queued and running work. On cancel, mark the job `cancelled`, terminate the process group if present, remove the temporary source and incomplete output directory, and release the reserved document name. A normal completion continues to preserve all page outputs. A completed or failed job is not changed by a later cancel request.

## API contract

- Add `POST /api/ocr/jobs/{job_id}/cancel`.
- Return the current job record with status `cancelled` when cancellation succeeds; return the unchanged terminal record for an already completed, failed, or cancelled job.
- Add `cancelled` to job status types and keep progress fields available for the final poll.
- Cancellation of an unknown job returns 404.
- Process tracking and signaling must be race-safe when cancellation overlaps worker startup or normal completion.

## Frontend behavior

- Show a **Dừng OCR** button while a job is queued or running. Disable it while cancellation is being acknowledged and show the cancelled state after the API confirms it.
- While a job is queued or running, show the notice **“Vui lòng giữ cửa sổ trong quá trình xử lý. Không chuyển sang trang khác của web.”**
- If the Upload page unmounts while a job is queued or running, request cancellation so navigating to another web page does not leave OCR running out of view.
- Register a `pagehide` handler for the active job. Send the cancellation request with `fetch(..., { method: 'POST', keepalive: true })` so reload or tab close requests cancellation even while the page is unloading. Remove the handler when the job reaches a terminal state or the component unmounts.
- Polling stops on `completed`, `failed`, or `cancelled`. A transient polling error remains a connection warning and continues retrying; it does not imply that the backend stopped.
- Cancellation is best-effort if the browser or operating system kills the tab/network before the request reaches the API. The API remains authoritative for whether the job has stopped.

## Cleanup and failure handling

- The worker closes PaddleOCR-VL explicitly in a `finally` block.
- The API records worker failures distinctly from user cancellation and cleans temporary files and process tracking in all terminal paths.
- Cancellation removes only the output directory reserved for that job, after validating that its resolved path remains directly under `data/raw`.
- FastAPI graceful shutdown terminates any registered OCR process groups before exiting. Job state remains process-local as in the current design; recovery after an ungraceful API crash is outside this change.

## Boundaries

This change does not add parallel OCR jobs, persistent job storage, an OCR timeout, Ollama changes, or changes to approval/finalization. It does not promise cancellation after the API host has already become unreachable; in that case the UI reports the API connection problem and the host/operator must stop the API process.

## Acceptance checks

1. Stop a running multi-page OCR job from the Upload page; status becomes `cancelled`, all job processes exit, and OCR VRAM is released.
2. Reload or close the Upload page during a running job; the same cancellation path runs and releases OCR VRAM.
3. Cancel a queued job; it never starts and its temporary source and name reservation are cleaned.
4. Let a job complete; results remain available and a later cancel does not delete them.
5. Cause a worker error; status is `failed`, not `cancelled`, and temporary/process tracking is cleaned.
