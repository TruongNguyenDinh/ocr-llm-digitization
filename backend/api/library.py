"""Read-only access to finalized local documents."""
import json
import re
import shutil
import sqlite3
import tempfile
import unicodedata
import zipfile
from difflib import SequenceMatcher
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from typing import Literal
from backend.llm.document_chat import MAX_CHAT_CONTEXT_BYTES, chat_with_document
from backend.api.library_search import run_library_search
from backend.llm.ollama_client import OllamaError

router = APIRouter(prefix="/api/library")
ROOT = Path(__file__).resolve().parents[2] / "storage"
RAW_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw"
ALLOWED_LIBRARY_CATEGORIES = {"letter", "document", "official_letter", "meeting_minutes", "book"}
LEGACY_CATEGORY_GROUPS = {
    "letter": "letter", "email": "letter", "invitation": "letter",
    "notice": "official_letter", "announcement": "official_letter", "memo": "official_letter",
    "meeting_minutes": "meeting_minutes",
    "book": "book", "textbook": "book", "newspaper": "book", "magazine": "book",
}
MARKDOWN_LINK = re.compile(r"(?P<prefix>!\[[^\]]*\]\()(?P<target><[^>]*>|[^)\s]+)(?P<tail>[^)]*\))")
MARKDOWN_IMAGE_REFERENCE = re.compile(r"!\[(?P<alt>[^\]]*)\](?:\[(?P<label>[^\]]*)\])")
MARKDOWN_DEFINITION = re.compile(r"(?m)^(?P<prefix> {0,3}\[(?P<label>[^\]]+)\]:\s*)(?P<target><[^>]*>|[^\s]+)(?P<tail>.*)$")
HTML_IMAGE_SOURCE = re.compile(r"\bsrc\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)


class ChatMessage(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=12000)


class DocumentChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list, max_length=40)


@router.post('/{document_id}/chat')
def document_chat(document_id: str, request: DocumentChatRequest):
    row = record(document_id)
    if request.messages and (request.messages[0].role != 'user' or request.messages[-1].role != 'user'
            or any(message.role != ('user' if index % 2 == 0 else 'assistant') for index, message in enumerate(request.messages))):
        raise HTTPException(422, 'Lịch sử chat không hợp lệ.')
    if request.messages and request.messages[-1].content.lstrip().lower().startswith('/ai:'):
        question = request.messages[-1].content.lstrip()[4:].strip()
        if not question:
            raise HTTPException(422, 'Sau /AI: hãy nhập câu hỏi cần tìm.')
        try:
            return run_library_search(question)
        except OllamaError as exc:
            raise HTTPException(502, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(503, 'Không thể tìm kiếm thư viện lúc này.') from exc
    pages = [safe_file(filename).read_text(encoding='utf-8') for filename in json.loads(row['digitized_page_paths'])]
    try:
        messages = [item.model_dump() for item in request.messages]
        answer, model, context_used = chat_with_document(summary(row)['name'], pages, messages)
        return {
            'answer': answer,
            'model': model,
            'document_id': document_id,
            'context_used_bytes': context_used,
            'context_limit_bytes': MAX_CHAT_CONTEXT_BYTES,
        }
    except OllamaError as exc:
        raise HTTPException(502, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def safe_file(value: str, root: Path = ROOT) -> Path:
    path = Path(value).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise HTTPException(404, "Document file not found")
    return path


def records():
    database = ROOT / "metadata.sqlite3"
    if not database.is_file():
        return []
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(
            "SELECT * FROM documents WHERE review_status = 'finalized' ORDER BY created_at DESC, document_id DESC")]


def record(document_id: str):
    found = next((r for r in records() if r["document_id"] == document_id), None)
    if found is None:
        raise HTTPException(404, "Document not found")
    return found


def summary(row):
    source = Path(row["source_path"])
    name = source.parent.name if source.stem == "_source" else source.stem
    name = row.get("display_name") or name
    return {"document_id": row["document_id"], "name": name,
            "label_name": row["label_name"], "page_count": row["page_count"], "created_at": row["created_at"]}


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
                   if unicodedata.category(c) != "Mn")


@router.get("")
def search_documents(q: str = "", offset: int = 0, limit: int = 20, label_name: str | None = None):
    terms = normalize(q.strip()).split()
    matches = []
    for row in records():
        if label_name:
            if label_name not in ALLOWED_LIBRARY_CATEGORIES:
                continue
            stored_category = LEGACY_CATEGORY_GROUPS.get(row["label_name"], row["label_name"])
            if stored_category not in ALLOWED_LIBRARY_CATEGORIES:
                stored_category = "document"
            if stored_category != label_name:
                continue
        item = summary(row)
        metadata = " ".join(str(row.get(k) or "") for k in
                            ("label_name", "document_type", "sender", "recipient", "date_time"))
        text = item["name"] + " " + metadata
        if terms and not all(term in normalize(text) for term in terms):
            for filename in json.loads(row["digitized_page_paths"]):
                try:
                    text += "\n" + safe_file(filename).read_text(encoding="utf-8")
                except (HTTPException, OSError):
                    continue
        if all(term in normalize(text) for term in terms):
            matches.append(item)
    offset = max(0, offset)
    return {"items": matches[offset:offset + min(100, max(1, limit))], "total": len(matches)}


@router.get("/{document_id}")
def read_document(document_id: str):
    row = record(document_id)
    final_paths = json.loads(row["digitized_page_paths"])
    context_path = Path(row["digitized_dir"]) / "review_context.json"
    review_path = context_path if context_path.is_file() else next(
        (p for p in RAW_ROOT.glob("*/review.json") if _review_matches(p, row["review_id"])), None
    )
    review = {}
    if review_path:
        try:
            review = json.loads(review_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    original_pages = {p.get("page_id"): p for p in review.get("markdown_pages", [])}
    approved_output = review.get("approved_output", "llm")
    try:
        edit_log = json.loads((Path(row["digitized_dir"]) / "edit_log.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        edit_log = []
    pages = []
    for index, filename in enumerate(final_paths):
        markdown = safe_file(filename).read_text(encoding="utf-8")
        page_id = f"page_{index + 1:03d}"
        source = original_pages.get(page_id, {})
        llm = source.get("llm_markdown", "")
        ocr = source.get("ocr_markdown", "")
        llm_changes = []
        if approved_output == "llm":
            model_ranges = _diff_ranges(ocr, llm, "llm", edit_log, page_id)
            llm_changes = _map_ranges(llm, markdown, model_ranges)
        manual_base = llm if approved_output == "llm" else ocr
        manual_changes = _diff_ranges(manual_base, markdown, "user", edit_log, page_id)
        pages.append({"page_number": index + 1, "markdown": markdown,
                      "llm_changes": llm_changes, "manual_changes": manual_changes})
    return {**summary(row), "pages": pages}


def _safe_export_name(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return name[:120] or "document"


def _rewrite_local_image_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith(("/", "\\")):
        return value
    path = PurePosixPath(unquote(parsed.path.replace("\\", "/")))
    parts = tuple(part for part in path.parts if part not in {"", "."})
    if not parts or parts[0] != "images" or ".." in parts:
        return value
    rewritten_path = PurePosixPath("..", *parts).as_posix()
    return urlunsplit(("", "", quote(rewritten_path, safe="/@!$&'()*+,;=:-._~"), parsed.query, parsed.fragment))


def _rewrite_markdown_image_paths(markdown: str) -> str:
    definitions = {}
    for definition in MARKDOWN_DEFINITION.finditer(markdown):
        label = definition.group("label").casefold()
        target = definition.group("target")
        url = target[1:-1] if target.startswith("<") and target.endswith(">") else target
        definitions[label] = _rewrite_local_image_url(url)

    def inline_reference(match: re.Match[str]) -> str:
        label = (match.group("label") or match.group("alt")).casefold()
        target = definitions.get(label, "")
        return f"![{match.group('alt')}]({target})" if target else match.group(0)

    markdown = MARKDOWN_IMAGE_REFERENCE.sub(inline_reference, markdown)

    def rewrite_markdown_link(match: re.Match[str]) -> str:
        target = match.group("target")
        is_bracketed = target.startswith("<") and target.endswith(">")
        url = target[1:-1] if is_bracketed else target
        rewritten = _rewrite_local_image_url(url)
        if rewritten == url:
            return match.group(0)
        target_out = f"<{rewritten}>" if is_bracketed else rewritten
        return f"{match.group('prefix')}{target_out}{match.group('tail')}"

    rewritten = MARKDOWN_LINK.sub(rewrite_markdown_link, markdown)
    return HTML_IMAGE_SOURCE.sub(
        lambda match: f"src={match.group(1)}{_rewrite_local_image_url(match.group(2))}{match.group(1)}",
        rewritten,
    )


@router.get("/{document_id}/download")
def download_document(document_id: str):
    row = record(document_id)
    title = summary(row)["name"]
    filename = _safe_export_name(title)
    source_pdf = safe_file(row["origin_pdf_path"])
    digitized_root = Path(row["digitized_dir"]).resolve()
    if not digitized_root.is_relative_to(ROOT.resolve()):
        raise HTTPException(404, "Document files not found")

    temp_dir = Path(tempfile.mkdtemp(prefix="library-export-"))
    try:
        markdown = "\n\n---\n\n".join(
            safe_file(page_path).read_text(encoding="utf-8")
            for page_path in json.loads(row["digitized_page_paths"])
        )
        markdown_path = temp_dir / f"{filename}.md"
        archive_path = temp_dir / f"{filename}.zip"

        image_root = (digitized_root / "images").resolve()
        staged_images = temp_dir / "images"
        staged_images.mkdir(parents=True, exist_ok=True)
        if image_root.is_relative_to(digitized_root) and image_root.is_dir():
            for image_path in image_root.rglob("*"):
                try:
                    resolved_image = image_path.resolve(strict=True)
                except OSError:
                    continue
                if resolved_image.is_relative_to(image_root) and resolved_image.is_file():
                    archive_name = PurePosixPath("images", *image_path.relative_to(image_root).parts)
                    destination = temp_dir.joinpath(*archive_name.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(resolved_image, destination)

        markdown = _rewrite_markdown_image_paths(markdown)
        markdown_path.write_text(markdown, encoding="utf-8")

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(markdown_path, PurePosixPath("digitization", markdown_path.name).as_posix())
            archive.write(source_pdf, PurePosixPath("origin", source_pdf.name).as_posix())
            image_archive_root = temp_dir / "images"
            if image_archive_root.is_dir():
                for path in image_archive_root.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(temp_dir).as_posix())
    except HTTPException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(500, f"Không thể tạo gói tải xuống: {exc}") from exc

    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=f"{filename}.zip",
        background=BackgroundTask(shutil.rmtree, temp_dir, ignore_errors=True),
    )


def _review_matches(path: Path, review_id: str) -> bool:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("review_id") == review_id
    except (OSError, ValueError):
        return False


def _diff_ranges(before: str, after: str, actor: str, log: list[dict], page_id: str):
    entries = [item for item in log if item.get("actor") == actor and item.get("page_id") == page_id]
    result = []
    for tag, _i1, _i2, j1, j2 in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if tag == "equal" or j1 == j2:
            continue
        changed = after[j1:j2]
        entry = next((item for item in entries if item.get("after") and item["after"] in changed), None)
        if entry:
            title = (f"{entry.get('actor_name') or ('LLM' if actor == 'llm' else 'Người dùng')} · "
                     f"{entry.get('operation') or 'sửa'} {entry.get('content_type') or 'văn bản'}\n"
                     f"Trước: {entry.get('before', '')}\nSau: {entry.get('after', '')}")
        else:
            title = ("LLM chỉnh sửa" if actor == "llm" else "Người dùng chỉnh sửa") + f"\nTrước: {before[_i1:_i2]}\nSau: {changed}"
        result.append({"start": _utf16_offset(after, j1), "end": _utf16_offset(after, j2),
                       "_python_start": j1, "_python_end": j2,
                       "before": before[_i1:_i2], "after": changed, "title": title})
    return result


def _utf16_offset(text: str, offset: int) -> int:
    return len(text[:offset].encode("utf-16-le")) // 2


def _map_ranges(source: str, target: str, ranges: list[dict]):
    """Map model spans through unchanged sections into finalized Markdown."""
    mapped = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, source, target, autojunk=False).get_opcodes():
        if tag != "equal":
            continue
        for change in ranges:
            start = max(i1, int(change["_python_start"]))
            end = min(i2, int(change["_python_end"]))
            if start < end:
                mapped.append({k: v for k, v in {**change, "start": _utf16_offset(target, j1 + start - i1),
                               "end": _utf16_offset(target, j1 + end - i1)}.items() if not k.startswith("_python_")})
    return mapped


@router.get("/{document_id}/original")
def original(document_id: str):
    return FileResponse(safe_file(record(document_id)["origin_pdf_path"]), media_type="application/pdf")


@router.get("/{document_id}/assets/{asset_path:path}")
def asset(document_id: str, asset_path: str):
    row = record(document_id)
    root = Path(row["digitized_dir"]).resolve()
    if not root.is_relative_to(ROOT.resolve()):
        raise HTTPException(404, "Document file not found")
    try:
        return FileResponse(safe_file(str(root / asset_path), root))
    except HTTPException:
        # Older finalized documents may not have copied OCR crops yet.
        for review_path in RAW_ROOT.glob("*/review.json"):
            try:
                payload = json.loads(review_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if payload.get("review_id") != row["review_id"]:
                continue
            raw_root = review_path.parent.resolve()
            try:
                recovered = safe_file(str(raw_root / asset_path), raw_root)
            except HTTPException:
                break
            return FileResponse(recovered)
        raise HTTPException(404, "Document image not found")
