"""Background indexing status and retry endpoints for the local vector store."""

from concurrent.futures import Future, ThreadPoolExecutor
import logging
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from backend.llm.document_index import DocumentIndexer
from backend.llm.embedding_client import OllamaEmbeddingClient
from backend.llm.vector_store import LocalPassageIndex
from backend.storage.repository import SQLiteRepository


ROOT = Path(__file__).resolve().parents[2] / "storage"
router = APIRouter(prefix="/api/library")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="document-index")
_lock = RLock()
_service: DocumentIndexer | None = None
_jobs: dict[str, str] = {}
_futures: dict[str, Future] = {}
logger = logging.getLogger(__name__)


def _get_service() -> DocumentIndexer:
    global _service
    with _lock:
        if _service is None:
            repository = SQLiteRepository(ROOT / "metadata.sqlite3")
            vector_size = int(os.environ.get("OLLAMA_EMBEDDING_DIMENSIONS", "768"))
            index = LocalPassageIndex(ROOT / "vector_index", vector_size=vector_size)
            _service = DocumentIndexer(repository, index, OllamaEmbeddingClient(), storage_root=ROOT)
        return _service


def configure_indexer_for_process(service: DocumentIndexer | None) -> None:
    """Install the process-wide index service; intended for tests and app setup."""
    global _service
    with _lock:
        _service = service


def _get_status() -> dict[str, int]:
    return _get_service().repository.get_index_status()


def _run_document(document_id: str) -> None:
    try:
        _get_service().index_document(document_id)
    except Exception:
        logger.exception("Indexing finalized document %s failed", document_id)


def _run_backfill(job_id: str, rebuild: bool = False) -> None:
    with _lock:
        _jobs[job_id] = "running"
    try:
        result = _get_service().backfill_documents(rebuild=rebuild)
        with _lock:
            _jobs[job_id] = "failed" if result["failed"] else "completed"
    except Exception:
        logger.exception("Document indexing backfill failed")
        with _lock:
            _jobs[job_id] = "failed"


def schedule_document_index(document_id: str) -> None:
    _executor.submit(_run_document, document_id)


def _schedule_backfill(rebuild: bool = False) -> str:
    with _lock:
        active = next((job for job, future in _futures.items() if not future.done()), None)
        if active:
            return active
        job_id = uuid4().hex
        _jobs[job_id] = "queued"
        _futures[job_id] = _executor.submit(_run_backfill, job_id, rebuild)
        return job_id


@router.get("/index-status")
def get_index_status() -> dict[str, int]:
    try:
        return _get_status()
    except Exception as exc:
        logger.exception("Could not read document index status")
        raise HTTPException(503, "Không đọc được trạng thái chỉ mục tài liệu.") from exc


@router.post("/reindex", status_code=202)
def reindex_documents(rebuild: bool = False):
    try:
        job_id = _schedule_backfill(rebuild)
        return JSONResponse(status_code=202, content={"job_id": job_id, "status": "queued", "rebuild": rebuild})
    except Exception as exc:
        logger.exception("Could not schedule document index backfill")
        raise HTTPException(503, "Không thể bắt đầu lập chỉ mục tài liệu.") from exc


def start_startup_backfill() -> None:
    _schedule_backfill()
