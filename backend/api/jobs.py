from __future__ import annotations

from dataclasses import asdict, dataclass, field
from threading import RLock
from typing import Any, Literal


JobStatus = Literal["queued", "running", "completed", "failed"]


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


job_store = OCRJobStore()
