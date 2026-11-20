from __future__ import annotations

import mimetypes
import os
import re
import signal
import subprocess
import json
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from backend.api.library import router as library_router
from backend.api.review_source import render_source_page
from backend.api.jobs import OCRJob, TERMINAL_STATUSES, job_store
from backend.api.system_status import read_system_status
from backend.document_workflow import prepare_review_from_output
from backend.llm.markdown_review import (
    MarkdownMappingError,
    apply_approved_text,
    build_markdown_review,
    build_manual_markdown_review,
    build_human_markdown_review,
    shift_llm_changes,
)
from backend.llm.review_store import ReviewStoreError, load_review_draft
from backend.llm.workflow import LLMWorkflowError, load_labels
from backend.ocr_vl.pipeline import SUPPORTED_EXTENSIONS
from backend.storage.service import finalize_review


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPOSITORY_ROOT / "data" / "raw"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paddle-ocr")
_reservation_lock = RLock()
_reserved_names: set[str] = set()
_process_lock = RLock()
_job_futures: dict[str, Future[None]] = {}
_job_processes: dict[str, subprocess.Popen[str]] = {}
_job_sources: dict[str, Path] = {}
_cancel_requested: set[str] = set()


class LLMReviewRequest(BaseModel):
    document_name: str
    provider: Literal["gemini", "qwen"] = "qwen"


class ReviewEditLogEntry(BaseModel):
    actor: Literal["user", "llm"] = "user"
    actor_name: str | None = None
    operation: Literal["insert", "delete", "replace"] | None = None
    position_basis: str | None = None
    before_position: dict[str, int] | None = None
    after_position: dict[str, int] | None = None
    mirrored_before_position: dict[str, int] | None = None
    mirrored_after_position: dict[str, int] | None = None
    context_before: str | None = None
    context_after: str | None = None
    content_type: Literal["text", "formula"] = "text"
    page_id: str
    source_side: Literal["ocr", "llm"]
    timestamp: str
    before: str
    after: str
    mirrored_before: str
    mirrored_after: str


class FinalizeReviewRequest(BaseModel):
    content_format: Literal["text", "markdown"] = "text"
    label_code: str | None = None
    display_name: str | None = None
    source: Literal["ocr", "llm"]
    approved_pages: dict[str, str]
    edit_log: list[ReviewEditLogEntry] = Field(default_factory=list)


class ReviewPreviewPage(BaseModel):
    ocr_text: str
    llm_text: str


class ReviewPreviewRequest(BaseModel):
    content_format: Literal["text", "markdown"] = "text"
    pages: dict[str, ReviewPreviewPage]


def _safe_document_name(document_name: str) -> bool:
    return bool(re.fullmatch(r"[\w.-]{1,120}", document_name, flags=re.UNICODE)) and document_name not in {".", ".."}


def _browser_change_spans(markdown: str, changes: list[dict[str, int | str]]) -> list[dict[str, int | str]]:
    """Convert Python code-point offsets to JavaScript UTF-16 offsets for browser rendering."""
    converted: list[dict[str, int | str]] = []
    for change in changes:
        start = int(change["start"])
        end = int(change["end"])
        converted.append({
            **change,
            "start": len(markdown[:start].encode("utf-16-le")) // 2,
            "end": len(markdown[:end].encode("utf-16-le")) // 2,
        })
    return converted


def _terminate_job_process(process: subprocess.Popen[str], grace_seconds: float = 3.0) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def _remove_incomplete_output(document_name: str) -> None:
    root = OUTPUT_ROOT.resolve()
    candidate = (OUTPUT_ROOT / document_name).resolve()
    if candidate.parent == root and candidate.name == document_name and candidate.is_dir():
        import shutil

        shutil.rmtree(candidate, ignore_errors=True)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    yield
    with _process_lock:
        job_ids = list(_job_futures)
    for job_id in job_ids:
        _cancel_ocr_job(job_id)
    _executor.shutdown(wait=True, cancel_futures=True)


app = FastAPI(title="OCR Upload API", version="1.0.0", lifespan=_lifespan)
app.include_router(library_router)
allowed_origins = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}
allowed_origins.update(
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/api/system/status")
def get_system_status() -> dict[str, float | None]:
    return read_system_status()


def _safe_stem(filename: str) -> str:
    raw_stem = Path(filename).stem
    name = re.sub(r"[^\w.-]+", "_", raw_stem, flags=re.UNICODE)
    name = name.strip(". _")[:100].rstrip(". ")
    return name or "document"


def _reserve_document_name(stem: str) -> str:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    with _reservation_lock:
        candidate = stem
        suffix = 2
        while (OUTPUT_ROOT / candidate).exists() or candidate in _reserved_names:
            candidate = f"{stem}_{suffix}"
            suffix += 1
        _reserved_names.add(candidate)
    return candidate


def _release_document_name(name: str) -> None:
    with _reservation_lock:
        _reserved_names.discard(name)


def _read_markdown_pages(document_name: str) -> list[dict[str, Any]]:
    document_dir = OUTPUT_ROOT / document_name
    if not document_dir.is_dir():
        return []
    markdown_files = sorted(document_dir.glob("page_*.md"))
    pages = []
    for path in markdown_files:
        match = re.fullmatch(r"page_(\d+)\.md", path.name)
        if match:
            pages.append(
                {"page_number": int(match.group(1)), "markdown": path.read_text(encoding="utf-8")}
            )
    return pages


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_ocr_job(job_id: str, source_path: Path, document_name: str) -> None:
    process: subprocess.Popen[str] | None = None
    try:
        with _process_lock:
            current = job_store.get(job_id)
            if current is None or current.status in TERMINAL_STATUSES:
                return
            now = _utc_timestamp()
            job_store.update_if_active(
                job_id,
                status="running",
                document_name=document_name,
                stage="worker_startup",
                stage_message="Worker đang khởi động và kiểm tra tài liệu.",
                stage_started_at=now,
                last_activity_at=now,
            )

        process = subprocess.Popen(
            [
                os.sys.executable,
                "-m",
                "backend.ocr_vl.worker",
                "--source",
                os.fspath(source_path),
                "--output-root",
                os.fspath(OUTPUT_ROOT),
            ],
            cwd=REPOSITORY_ROOT,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        with _process_lock:
            _job_processes[job_id] = process
            current = job_store.get(job_id)
            should_cancel = job_id in _cancel_requested or current is None or current.status in TERMINAL_STATUSES
        if should_cancel:
            _terminate_job_process(process)

        failure_message: str | None = None
        assert process.stdout is not None
        for line in process.stdout:
            if not line.startswith("OCR_EVENT:"):
                diagnostic_line = line.strip()
                if diagnostic_line:
                    job_store.add_diagnostic(job_id, diagnostic_line[:500])
                    job_store.update_if_active(job_id, last_activity_at=_utc_timestamp())
                continue
            try:
                event = json.loads(line[len("OCR_EVENT:"):])
            except (ValueError, TypeError):
                continue
            if not isinstance(event, dict):
                continue
            now = _utc_timestamp()
            stage = event.get("stage")
            snapshot = job_store.get(job_id)
            changes: dict[str, Any] = {"last_activity_at": now}
            if isinstance(stage, str) and stage:
                changes["stage"] = stage
                changes["stage_message"] = str(event.get("message") or stage)
                if snapshot is None or snapshot.stage != stage:
                    changes["stage_started_at"] = now
            if isinstance(event.get("page_number"), int):
                changes["current_page"] = event["page_number"]
            if event.get("event") == "page_completed":
                changes["current_page"] = event.get("page_number")
            if changes:
                job_store.update_if_active(job_id, **changes)
            if event.get("event") == "processing_started":
                job_store.update_if_active(
                    job_id,
                    document_name=event.get("document_name", document_name),
                    completed_pages=0,
                    total_pages=event.get("total"),
                )
            elif event.get("event") == "page_completed":
                job_store.update_if_active(
                    job_id,
                    completed_pages=event.get("completed", 0),
                    total_pages=event.get("total"),
                )
            elif event.get("event") == "failed":
                failure_message = str(event.get("error") or "PaddleOCR-VL failed.")

        return_code = process.wait()
        with _process_lock:
            snapshot = job_store.get(job_id)
            if snapshot is not None and snapshot.status == "cancelled":
                return
            if return_code == 0:
                source_archive = OUTPUT_ROOT / document_name / f"_source{source_path.suffix}"
                os.replace(source_path, source_archive)
            pages = _read_markdown_pages(document_name)
            if return_code == 0:
                job_store.finish(
                    job_id, "completed", document_name=document_name,
                    completed_pages=len(pages), total_pages=len(pages), pages=pages,
                    stage="completed", stage_message="OCR đã xử lý xong toàn bộ tài liệu.",
                    stage_started_at=_utc_timestamp(), last_activity_at=_utc_timestamp(),
                )
            else:
                job_store.finish(
                    job_id, "failed",
                    completed_pages=snapshot.completed_pages if snapshot else len(pages),
                    pages=pages,
                    error=failure_message or f"OCR worker exited with code {return_code}.",
                    stage="failed", stage_message="OCR worker đã dừng do lỗi.",
                    stage_started_at=_utc_timestamp(), last_activity_at=_utc_timestamp(),
                )
    except Exception as exc:
        if process is not None:
            _terminate_job_process(process)
        job_store.finish(
            job_id, "failed", error=str(exc), stage="failed",
            stage_message="API gặp lỗi khi theo dõi worker OCR.",
            stage_started_at=_utc_timestamp(), last_activity_at=_utc_timestamp(),
        )
    finally:
        if process is not None and process.stdout is not None:
            process.stdout.close()
        source_path.unlink(missing_ok=True)
        with _process_lock:
            _job_processes.pop(job_id, None)
            _job_futures.pop(job_id, None)
            _job_sources.pop(job_id, None)
            _cancel_requested.discard(job_id)
        current = job_store.get(job_id)
        if current is not None and current.status == "cancelled":
            _remove_incomplete_output(document_name)
        _release_document_name(document_name)


def _cancel_ocr_job(job_id: str) -> dict[str, Any]:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="OCR job not found.")
    if job.status in TERMINAL_STATUSES:
        return job.as_response()

    with _process_lock:
        completed_process = _job_processes.get(job_id)
        running_future = _job_futures.get(job_id)
    if completed_process is not None and completed_process.poll() is not None and running_future is not None:
        try:
            running_future.result(timeout=5)
        except FutureTimeoutError:
            pass
        job = job_store.get(job_id)
        if job is not None and job.status in TERMINAL_STATUSES:
            return job.as_response()

    with _process_lock:
        job = job_store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="OCR job not found.")
        if job.status in TERMINAL_STATUSES:
            return job.as_response()
        _cancel_requested.add(job_id)
        process = _job_processes.get(job_id)
        future = _job_futures.get(job_id)
        source_path = _job_sources.get(job_id)
        job_store.finish(
            job_id, "cancelled", error=None, stage="cancelled",
            stage_message="OCR đã bị dừng theo yêu cầu.",
            stage_started_at=_utc_timestamp(), last_activity_at=_utc_timestamp(),
        )
        future_cancelled = future.cancel() if future is not None else False
        if future_cancelled:
            _job_futures.pop(job_id, None)
            _job_sources.pop(job_id, None)
            _cancel_requested.discard(job_id)

    if process is not None:
        _terminate_job_process(process)
        if future is not None:
            try:
                future.result(timeout=5)
            except FutureTimeoutError:
                pass
    if future_cancelled:
        if source_path is not None:
            source_path.unlink(missing_ok=True)
        _release_document_name(job.document_name or "")
    if job.document_name:
        _remove_incomplete_output(job.document_name)
        _release_document_name(job.document_name)
    return job_store.get(job_id).as_response()


@app.post("/api/ocr/jobs", status_code=202)
async def create_ocr_job(file: UploadFile = File(...)) -> dict[str, str]:
    original_filename = (file.filename or "").replace("\\", "/")
    filename = PurePosixPath(original_filename).name
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type. Supported extensions: {supported}",
        )

    stem = _safe_stem(filename)
    document_name = _reserve_document_name(stem)
    source_path: Path | None = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix="ocr-upload-", suffix=suffix
        )
        source_path = Path(temp_name)
        size = 0
        with os.fdopen(descriptor, "wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 100 MiB upload limit.",
                    )
                destination.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        # The OCR pipeline derives its output folder from the source file stem.
        named_source = source_path.with_name(f"{document_name}{suffix}")
        source_path.rename(named_source)
        source_path = named_source
        job_id = uuid.uuid4().hex
        job_store.add(OCRJob(job_id=job_id, filename=filename, document_name=document_name))
        with _process_lock:
            _job_sources[job_id] = source_path
            future = _executor.submit(_run_ocr_job, job_id, source_path, document_name)
            _job_futures[job_id] = future
        source_path = None
        return {"job_id": job_id}
    except HTTPException:
        _release_document_name(document_name)
        if source_path is not None:
            source_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        _release_document_name(document_name)
        if source_path is not None:
            source_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not accept upload: {exc}") from exc
    finally:
        await file.close()


@app.get("/api/ocr/jobs/{job_id}")
def get_ocr_job(job_id: str) -> dict[str, Any]:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="OCR job not found.")
    return job.as_response()


@app.post("/api/ocr/jobs/{job_id}/cancel")
def cancel_ocr_job(job_id: str) -> dict[str, Any]:
    return _cancel_ocr_job(job_id)


@app.post("/api/llm/reviews")
def create_llm_review(request: LLMReviewRequest) -> dict[str, Any]:
    if not _safe_document_name(request.document_name):
        raise HTTPException(status_code=400, detail="Invalid document name.")
    document_dir = (OUTPUT_ROOT / request.document_name).resolve()
    if document_dir.parent != OUTPUT_ROOT.resolve() or not document_dir.is_dir():
        raise HTTPException(status_code=404, detail="Completed OCR document not found.")
    try:
        review_path = document_dir / "review.json"
        if review_path.exists():
            saved = json.loads(review_path.read_text(encoding="utf-8"))
            if saved.get("status") != "pending_review" or saved.get("provider") != request.provider:
                raise HTTPException(status_code=409, detail="An existing review has a different provider or is already finalized.")
            draft = load_review_draft(saved["review_id"], output_root=OUTPUT_ROOT)
        else:
            draft = prepare_review_from_output(
                request.document_name,
                provider=request.provider,
                output_root=OUTPUT_ROOT,
            )
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LLMWorkflowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (MarkdownMappingError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not prepare LLM review: {exc}") from exc
    payload = draft.to_dict()
    for page in payload.get("markdown_pages", []):
        if isinstance(page, dict):
            page["llm_changes"] = _browser_change_spans(
                str(page.get("llm_markdown", "")), page.get("llm_changes", [])
            )
    payload.pop("source_path", None)
    payload.pop("raw_document_dir", None)
    return payload


@app.get("/api/llm/labels")
def get_review_labels() -> dict[str, str]:
    return load_labels()


@app.get("/api/llm/reviews/{review_id}/original/{page_id}")
def get_review_original_page(review_id: str, page_id: str) -> Response:
    try:
        draft = load_review_draft(review_id, output_root=OUTPUT_ROOT)
        ids = [page.page_id for page in draft.pages]
        if page_id not in ids:
            raise HTTPException(status_code=404, detail="Original page not found.")
        source = Path(draft.source_path)
        image = render_source_page(str(source), source.stat().st_mtime_ns, ids.index(page_id))
        return Response(image, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})
    except (FileNotFoundError, IndexError, EOFError) as exc:
        raise HTTPException(status_code=404, detail="Original document is unavailable.") from exc
    except ReviewStoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/llm/reviews/{review_id}/finalize")
def finalize_llm_review(review_id: str, request: FinalizeReviewRequest) -> dict[str, object]:
    try:
        draft = load_review_draft(review_id, output_root=OUTPUT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReviewStoreError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    expected_ids = [page.page_id for page in draft.pages]
    if set(request.approved_pages) != set(expected_ids):
        raise HTTPException(status_code=422, detail="Approved content must include every review page exactly once.")
    markdown_by_id = {page.page_id: page for page in (draft.markdown_pages or [])}
    if set(markdown_by_id) != set(expected_ids):
        raise HTTPException(status_code=422, detail="Review is missing its OCR Markdown pages.")
    approved_markdown: dict[str, str] = {}
    try:
        for page in draft.pages:
            markdown_page = markdown_by_id[page.page_id]
            if request.content_format == "markdown":
                approved_markdown[page.page_id] = request.approved_pages[page.page_id]
                continue
            approved_markdown[page.page_id] = apply_approved_text(
                markdown_page.ocr_markdown,
                page.raw_text,
                request.approved_pages[page.page_id],
            )
    except MarkdownMappingError as exc:
        raise HTTPException(status_code=422, detail=f"Could not preserve Markdown structure: {exc}") from exc

    user_id = os.environ.get("DIGITIZATION_USER_ID", "local_user").strip() or "local_user"
    try:
        return finalize_review(
            review_id,
            user_id,
            approved_markdown,
            storage_root=REPOSITORY_ROOT / "storage",
            review_root=OUTPUT_ROOT,
            chosen_output=request.source,
            approved_label_code=request.label_code,
            edit_log=[item.model_dump() for item in request.edit_log],
            display_name=request.display_name,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not finalize review: {exc}") from exc


@app.post("/api/llm/reviews/{review_id}/preview")
def preview_llm_review(review_id: str, request: ReviewPreviewRequest) -> dict[str, Any]:
    try:
        draft = load_review_draft(review_id, output_root=OUTPUT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    markdown_by_id = {page.page_id: page for page in (draft.markdown_pages or [])}
    pages_by_id = {page.page_id: page for page in draft.pages}
    if set(request.pages) != set(pages_by_id):
        raise HTTPException(status_code=422, detail="Preview must include every review page exactly once.")
    result: list[dict[str, Any]] = []
    try:
        for page_id, content in request.pages.items():
            raw_page = pages_by_id[page_id]
            markdown_page = markdown_by_id[page_id]
            if request.content_format == "markdown":
                ocr_preview = build_human_markdown_review(markdown_page.ocr_markdown, content.ocr_text)
                manual_llm = build_human_markdown_review(markdown_page.llm_markdown, content.llm_text)
            else:
                ocr_preview = build_manual_markdown_review(
                    markdown_page.ocr_markdown, raw_page.raw_text, content.ocr_text
                )
                manual_llm = build_manual_markdown_review(
                    markdown_page.llm_markdown, raw_page.corrected_text, content.llm_text
                )
            llm_changes = shift_llm_changes(markdown_page.llm_changes, manual_llm.llm_changes)
            result.append({
                "page_id": page_id,
                "ocr_markdown": ocr_preview.llm_markdown,
                "llm_markdown": manual_llm.llm_markdown,
                "ocr_manual_changes": _browser_change_spans(
                    ocr_preview.llm_markdown,
                    [change.to_dict() for change in ocr_preview.llm_changes],
                ),
                "llm_changes": _browser_change_spans(manual_llm.llm_markdown, llm_changes),
                "llm_manual_changes": _browser_change_spans(
                    manual_llm.llm_markdown,
                    [change.to_dict() for change in manual_llm.llm_changes],
                ),
            })
    except MarkdownMappingError as exc:
        raise HTTPException(status_code=422, detail=f"Could not preserve Markdown structure: {exc}") from exc
    return {"pages": result}


@app.get("/api/ocr/documents/{document_name}/{asset_path:path}")
def get_document_asset(document_name: str, asset_path: str) -> FileResponse:
    root = OUTPUT_ROOT.resolve()
    if not re.fullmatch(r"[\w.-]+", document_name) or document_name in {".", ".."}:
        raise HTTPException(status_code=404, detail="Document asset not found.")
    document_dir = (root / document_name).resolve()
    target = (document_dir / asset_path).resolve()
    if document_dir.parent != root or not target.is_relative_to(document_dir):
        raise HTTPException(status_code=404, detail="Document asset not found.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Document asset not found.")
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type)
