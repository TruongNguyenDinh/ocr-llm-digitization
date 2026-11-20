import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .comparison import PageComparison
from .schemas import CorrectedPage, DocumentMetadata, ReviewDraft, ReviewMarkdownPage


class ReviewStoreError(RuntimeError):
    """Raised when a review draft cannot be safely persisted or loaded."""


def save_review_draft(
    raw_document_dir: str | Path,
    draft: ReviewDraft,
    comparisons: Iterable[PageComparison],
) -> Path:
    directory = Path(raw_document_dir)
    if not directory.is_dir():
        raise ReviewStoreError(f"Raw document directory does not exist: {directory}")
    review_path = directory / "review.json"
    if review_path.exists():
        raise FileExistsError(f"Review record already exists: {review_path}")

    payload: dict[str, Any] = draft.to_dict()
    payload["comparisons"] = [item.to_dict() for item in comparisons]
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".review-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        # A hard link publishes atomically and fails rather than overwriting a record.
        os.link(temporary_path, review_path)
        temporary_path.unlink()
        return review_path
    except FileExistsError:
        raise FileExistsError(f"Review record already exists: {review_path}") from None
    except Exception as exc:
        raise ReviewStoreError(f"Could not save review record {review_path}: {exc}") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def set_review_status(
    review_path: str | Path,
    expected_status: str,
    new_status: str,
    updates: dict[str, Any] | None = None,
) -> bytes:
    """Atomically update status and return the original bytes for rollback."""
    path = Path(review_path)
    original = path.read_bytes()
    try:
        payload = json.loads(original.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ReviewStoreError(f"Review record {path} is invalid: {exc}") from exc
    if payload.get("status") != expected_status:
        raise ReviewStoreError(
            f"Review {payload.get('review_id')} has status {payload.get('status')!r}, "
            f"expected {expected_status!r}"
        )
    payload["status"] = new_status
    if updates:
        payload.update(updates)
    _replace_bytes_atomically(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    return original


def restore_review_record(review_path: str | Path, contents: bytes) -> None:
    """Restore a review record after its matching database transaction rolls back."""
    _replace_bytes_atomically(Path(review_path), contents)


def _replace_bytes_atomically(path: Path, contents: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(contents)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    except Exception as exc:
        raise ReviewStoreError(f"Could not atomically update review {path}: {exc}") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def load_review_draft(
    review_id: str,
    output_root: str | Path = "data/raw",
) -> ReviewDraft:
    root = Path(output_root)
    for review_path in root.glob("*/review.json"):
        try:
            payload = json.loads(review_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ReviewStoreError(f"Could not read review record {review_path}: {exc}") from exc
        if payload.get("review_id") != review_id:
            continue
        if payload.get("status") != "pending_review":
            raise ReviewStoreError(f"Review {review_id} is not pending review")
        try:
            return ReviewDraft(
                review_id=payload["review_id"],
                document_name=payload["document_name"],
                source_path=payload["source_path"],
                raw_document_dir=payload["raw_document_dir"],
                page_count=int(payload["page_count"]),
                pages=[CorrectedPage(**page) for page in payload["pages"]],
                metadata=DocumentMetadata(**payload["metadata"]),
                provider=str(payload.get("provider", "qwen")),
                model=str(payload.get("model", "qwen3:8b")),
                markdown_pages=[
                    ReviewMarkdownPage(**page)
                    for page in payload.get("markdown_pages", [])
                ],
                status=payload["status"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ReviewStoreError(f"Review record {review_path} is invalid: {exc}") from exc
    raise FileNotFoundError(f"Pending review not found: {review_id}")
