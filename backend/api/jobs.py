from __future__ import annotations

from dataclasses import asdict, dataclass, field
from threading import RLock
from typing import Any, Literal


JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


@dataclass
class OCRJob:
    job_id: str
    filename: str
    status: JobStatus = "queued"
    document_name: str | None = None
    completed_pages: int = 0
    total_pages: int | None = None
    pages: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    stage: str = "queued"
    stage_message: str = "Đang chờ worker OCR."
    stage_started_at: str | None = None
    last_activity_at: str | None = None
    current_page: int | None = None
    diagnostics: list[str] = field(default_factory=list)

    def as_response(self) -> dict[str, Any]:
        return asdict(self)


class OCRJobStore:
    """Thread-safe, process-local state for queued and active OCR jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, OCRJob] = {}
        self._lock = RLock()

    def add(self, job: OCRJob) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def get(self, job_id: str) -> OCRJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return OCRJob(**job.as_response()) if job is not None else None

    def update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)

    def update_if_active(self, job_id: str, **changes: Any) -> bool:
        """Apply a state/progress update unless this job has already terminated."""
        with self._lock:
            job = self._jobs[job_id]
            if job.status in TERMINAL_STATUSES:
                return False
            for key, value in changes.items():
                setattr(job, key, value)
            return True

    def finish(self, job_id: str, status: JobStatus, **changes: Any) -> bool:
        """Record the first terminal result; later races cannot replace it."""
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"Not a terminal OCR job status: {status}")
        with self._lock:
            job = self._jobs[job_id]
            if job.status in TERMINAL_STATUSES:
                return False
            job.status = status
            for key, value in changes.items():
                setattr(job, key, value)
            return True

    def add_diagnostic(self, job_id: str, line: str, limit: int = 12) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in TERMINAL_STATUSES:
                return
            job.diagnostics.append(line)
            del job.diagnostics[:-limit]


job_store = OCRJobStore()
