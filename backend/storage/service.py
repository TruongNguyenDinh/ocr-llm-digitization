from dataclasses import replace, asdict
from backend.llm.workflow import load_labels

import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlsplit

from PIL import Image, ImageOps

from backend.llm.review_store import (
    load_review_draft,
    restore_review_record,
    set_review_status,
)

from .repository import SQLiteRepository


_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_HTML_IMAGE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)
logger = logging.getLogger(__name__)


def _validate_component(value: str, name: str) -> str:
    if not _SAFE_COMPONENT.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"Unsafe {name}: {value!r}")
    return value


def _to_rgb(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if image.mode == "RGB":
        return image.copy()
    if "A" in image.getbands():
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def _write_origin_pdf(source_path: Path, destination: Path) -> None:
    if source_path.suffix.lower() == ".pdf":
        shutil.copyfile(source_path, destination)
        return

    converted_pages: list[Image.Image] = []
    try:
        with Image.open(source_path) as source_image:
            frame_count = int(getattr(source_image, "n_frames", 1))
            for frame_number in range(frame_count):
                source_image.seek(frame_number)
                converted_pages.append(_to_rgb(source_image.copy()))
        if not converted_pages:
            raise ValueError(f"Image contains no frames: {source_path}")
        converted_pages[0].save(
            destination,
            format="PDF",
            save_all=True,
            append_images=converted_pages[1:],
            resolution=200.0,
        )
    finally:
        for page in converted_pages:
            page.close()


def _copy_markdown_assets(
    approved_pages: Mapping[str, str],
    raw_document_dir: Path,
    destination_dir: Path,
    published_paths: list[Path],
    published_directories: list[Path],
) -> dict[str, str]:
    raw_root = raw_document_dir.resolve()
    destination_root = destination_dir.resolve()
    copied: set[Path] = set()
    rewritten: dict[str, str] = {}
    for markdown in approved_pages.values():
        references = [(match, match.group(1), "markdown") for match in _MARKDOWN_LINK.finditer(markdown)]
        references.extend((match, match.group(2), "html") for match in _HTML_IMAGE.finditer(markdown))
        for match, raw_target, kind in references:
            target_text = raw_target.strip().split(maxsplit=1)[0].strip("<>") if kind == "markdown" else raw_target.strip()
            parsed = urlsplit(target_text)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            relative_path = Path(unquote(parsed.path))
            source = (raw_root / relative_path).resolve()
            if not source.is_relative_to(raw_root) or not source.exists():
                continue
            target = (destination_root / "images" / relative_path).resolve()
            if not target.is_relative_to(destination_root / "images"):
                continue
            original_reference = target_text
            rewritten[original_reference] = (Path("images") / relative_path).as_posix()
            if target in copied:
                continue
            copied.add(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            parent = target.parent
            while parent != destination_root:
                if parent not in published_directories:
                    published_directories.append(parent)
                parent = parent.parent
            if source.is_dir():
                published_directories.append(target)
                published_paths.extend(path for path in target.rglob("*") if path.is_file())
                published_directories.extend(path for path in target.rglob("*") if path.is_dir())
                shutil.copytree(source, target)
            elif source.is_file():
                published_paths.append(target)
                shutil.copyfile(source, target)
    return rewritten


def _remove_published(paths: list[Path], directories: list[Path]) -> list[str]:
    cleanup_errors: list[str] = []
    for path in reversed(paths):
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            cleanup_errors.append(f"{path}: {exc}")
    for directory in reversed(directories):
        try:
            directory.rmdir()
        except OSError as exc:
            cleanup_errors.append(f"{directory}: {exc}")
    return cleanup_errors


def finalize_review(
    review_id: str,
    user_id: str,
    approved_pages: Mapping[str, str],
    storage_root: str | Path = "storage",
    repository: SQLiteRepository | None = None,
    review_root: str | Path = "data/raw",
    chosen_output: str | None = None,
    approved_label_code: str | None = None,
    edit_log: Sequence[Mapping[str, Any]] = (),
    display_name: str | None = None,
) -> dict[str, object]:
    """Persist only user-approved page text and one source PDF per document."""
    safe_user_id = _validate_component(user_id, "user_id")
    draft = load_review_draft(review_id, output_root=review_root)
    original_metadata = draft.metadata
    if approved_label_code is not None:
        labels = load_labels()
        if approved_label_code not in labels:
            raise ValueError("Unknown approved label code")
        if approved_label_code != draft.metadata.label_code:
            draft = replace(draft, metadata=replace(draft.metadata,
                label_code=approved_label_code, label_name=labels[approved_label_code],
                document_type=labels[approved_label_code]))
            edit_log = [*edit_log, {
                "actor": "user", "actor_name": safe_user_id,
                "content_type": "classification", "operation": "replace",
                "scope": "document", "timestamp": datetime.now(timezone.utc).isoformat(),
                "before": asdict(original_metadata), "after": asdict(draft.metadata),
            }]
    review_path = Path(draft.raw_document_dir) / "review.json"
    safe_label = _validate_component(draft.metadata.label_code, "label code")
    expected_page_ids = [page.page_id for page in draft.pages]
    if set(approved_pages) != set(expected_page_ids):
        raise ValueError(
            "approved_pages must contain exactly these page IDs: "
            + ", ".join(expected_page_ids)
        )
    if any(not isinstance(text, str) for text in approved_pages.values()):
        raise TypeError("Every approved page value must be text")
    if chosen_output not in {None, "ocr", "llm"}:
        raise ValueError("chosen_output must be 'ocr', 'llm', or None")

    source_path = Path(draft.source_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"Original source file is missing: {source_path}")
    saved_name = (display_name or source_path.stem).strip()
    if not saved_name or len(saved_name) > 200:
        raise ValueError("Saved document name must contain 1 to 200 characters")

    root = Path(storage_root)
    root.mkdir(parents=True, exist_ok=True)
    repo = repository or SQLiteRepository(root / "metadata.sqlite3")
    published_paths: list[Path] = []
    published_directories: list[Path] = []
    result: dict[str, object] | None = None
    review_backup: bytes | None = None

    try:
        with tempfile.TemporaryDirectory(prefix=".finalize-", dir=root) as temp_name:
            staging_root = Path(temp_name)
            staged_pages_dir = staging_root / "pages"
            staged_pages_dir.mkdir()
            staged_page_paths: list[Path] = []
            for page in draft.pages:
                staged_page = staged_pages_dir / f"{page.page_id}.md"
                staged_page.write_text(approved_pages[page.page_id], encoding="utf-8")
                staged_page_paths.append(staged_page)

            staged_pdf = staging_root / "origin.pdf"
            _write_origin_pdf(source_path, staged_pdf)
            staged_edit_log = staging_root / "edit_log.json"
            staged_edit_log.write_text(
                json.dumps(list(edit_log), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            staged_review_context = staging_root / "review_context.json"
            staged_review_context.write_text(
                json.dumps({
                    "review_id": draft.review_id,
                    "markdown_pages": [asdict(page) for page in (draft.markdown_pages or [])],
                    "approved_output": chosen_output or "llm",
                    "original_metadata": asdict(original_metadata),
                    "metadata": asdict(draft.metadata),
                    "edit_log": list(edit_log),
                }, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with repo.transaction() as connection:
                sequence = repo.next_sequence(connection, safe_user_id)
                document_id = f"{safe_user_id}_{sequence:06d}"
                digitized_dir = root / "digitization" / safe_label / document_id
                origin_pdf = root / "origin" / safe_label / f"{document_id}.pdf"
                if digitized_dir.exists() or origin_pdf.exists():
                    raise FileExistsError(
                        f"Final storage path already exists for {document_id}"
                    )

                digitized_dir.parent.mkdir(parents=True, exist_ok=True)
                origin_pdf.parent.mkdir(parents=True, exist_ok=True)
                digitized_dir.mkdir()
                published_directories.append(digitized_dir)

                asset_rewrites = _copy_markdown_assets(
                    approved_pages,
                    Path(draft.raw_document_dir),
                    digitized_dir,
                    published_paths,
                    published_directories,
                )

                for staged_page in staged_page_paths:
                    markdown = staged_page.read_text(encoding="utf-8")
                    for original, stored in asset_rewrites.items():
                        markdown = markdown.replace(original, stored)
                    staged_page.write_text(markdown, encoding="utf-8")

                final_page_paths: list[Path] = []
                for staged_page in staged_page_paths:
                    final_page = digitized_dir / staged_page.name
                    os.link(staged_page, final_page)
                    published_paths.append(final_page)
                    final_page_paths.append(final_page)
                os.link(staged_pdf, origin_pdf)
                published_paths.append(origin_pdf)
                final_edit_log = digitized_dir / "edit_log.json"
                os.link(staged_edit_log, final_edit_log)
                published_paths.append(final_edit_log)
                final_review_context = digitized_dir / "review_context.json"
                os.link(staged_review_context, final_review_context)
                published_paths.append(final_review_context)

                metadata = draft.metadata
                record = {
                    "document_id": document_id,
                    "review_id": draft.review_id,
                    "user_id": safe_user_id,
                    "sequence": sequence,
                    "display_name": saved_name,
                    "label_code": metadata.label_code,
                    "label_name": metadata.label_name,
                    "sender": metadata.sender,
                    "recipient": metadata.recipient,
                    "date_time": metadata.date_time,
                    "document_type": metadata.document_type,
                    "page_count": draft.page_count,
                    "source_path": str(source_path.resolve()),
                    "digitized_dir": str(digitized_dir),
                    "digitized_page_paths": [str(path) for path in final_page_paths],
                    "origin_pdf_path": str(origin_pdf),
                    "review_status": "finalized",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                repo.insert_document(connection, record)
                review_backup = set_review_status(
                    review_path,
                    expected_status="pending_review",
                    new_status="finalized",
                    updates={
                        "approved_output": chosen_output,
                        "display_name": saved_name,
                        "original_metadata": asdict(original_metadata),
                        "metadata": asdict(draft.metadata),
                        "edit_log": list(edit_log),
                    },
                )
                result = {
                    "document_id": document_id,
                    "user_id": safe_user_id,
                    "sequence": sequence,
                    "display_name": saved_name,
                    "created_at": record["created_at"],
                    "label_code": metadata.label_code,
                    "label_name": metadata.label_name,
                    "digitized_dir": str(digitized_dir),
                    "digitized_page_paths": [str(path) for path in final_page_paths],
                    "origin_pdf_path": str(origin_pdf),
                    "edit_log_path": str(final_edit_log),
                }
    except Exception as exc:
        rollback_errors: list[str] = []
        if review_backup is not None:
            try:
                restore_review_record(review_path, review_backup)
            except Exception as rollback_exc:
                rollback_errors.append(f"review record {review_path}: {rollback_exc}")
        cleanup_errors = _remove_published(published_paths, published_directories)
        if cleanup_errors or rollback_errors:
            raise RuntimeError(
                f"Could not finalize review {review_id}: {exc}; "
                "rollback/cleanup also failed for "
                + "; ".join(rollback_errors + cleanup_errors)
            ) from exc
        if isinstance(exc, (ValueError, TypeError, FileNotFoundError, FileExistsError)):
            raise
        raise RuntimeError(f"Could not finalize review {review_id}: {exc}") from exc

    if result is None:
        raise RuntimeError(f"Review {review_id} was not finalized")
    raw_dir = Path(draft.raw_document_dir)
    raw_root = Path(review_root).resolve()
    resolved_raw_dir = raw_dir.resolve()
    if not raw_dir.is_symlink() and resolved_raw_dir.parent == raw_root and resolved_raw_dir.is_dir():
        try:
            shutil.rmtree(resolved_raw_dir)
        except OSError as exc:
            logger.warning("Finalized review was saved, but its temporary OCR folder could not be removed: %s", exc)
    return result


def get_digitized_document(
    document_id: str,
    storage_root: str | Path = "storage",
    repository: SQLiteRepository | None = None,
) -> dict[str, object] | None:
    """Load persisted metadata and file locations for a future web caller."""
    repo = repository or SQLiteRepository(Path(storage_root) / "metadata.sqlite3")
    return repo.get_document(document_id)
