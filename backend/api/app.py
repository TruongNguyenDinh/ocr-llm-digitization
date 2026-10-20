from __future__ import annotations

import mimetypes
import os
import re
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.api.jobs import OCRJob, job_store
from backend.api.system_status import read_system_status
from backend.ocr_vl.pipeline import SUPPORTED_EXTENSIONS, process_document


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPOSITORY_ROOT / "data" / "raw"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paddle-ocr")
_reservation_lock = RLock()
_reserved_names: set[str] = set()

app = FastAPI(title="OCR Upload API", version="1.0.0")
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


def _run_ocr_job(job_id: str, source_path: Path, document_name: str) -> None:
    job_store.update(job_id, status="running", document_name=document_name)

    def on_progress(event: dict[str, Any]) -> None:
        if event.get("event") == "processing_started":
            job_store.update(
                job_id,
                document_name=event["document_name"],
                completed_pages=0,
                total_pages=event["total"],
            )
        elif event.get("event") == "page_completed":
            job_store.update(
                job_id,
                completed_pages=event["completed"],
                total_pages=event["total"],
            )

    try:
        result = process_document(
            source_path,
            output_root=OUTPUT_ROOT,
            progress_callback=on_progress,
        )
        pages = _read_markdown_pages(result["document_name"])
        job_store.update(
            job_id,
            status="completed",
            document_name=result["document_name"],
            completed_pages=result["page_count"],
            total_pages=result["page_count"],
            pages=pages,
        )
    except Exception as exc:
        snapshot = job_store.get(job_id)
        pages = _read_markdown_pages(document_name)
        job_store.update(
            job_id,
            status="failed",
            completed_pages=snapshot.completed_pages if snapshot else len(pages),
            pages=pages,
            error=str(exc),
        )
    finally:
        source_path.unlink(missing_ok=True)
        _release_document_name(document_name)


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
        _executor.submit(_run_ocr_job, job_id, source_path, document_name)
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
