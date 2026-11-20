import gc
import json
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from PIL import Image
from pypdf import PdfReader

from .engine import PaddleOCRVLEngine


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tiff",
    ".webp",
}
SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | {".pdf"}
ProgressCallback = Callable[[dict[str, Any]], None]


class OCREngine(Protocol):
    def predict(self, input_path: str | Path) -> Iterable[Any]: ...


def _validate_input(input_path: str | Path) -> Path:
    path = Path(input_path).expanduser()

    if not path.exists():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Input path is not a file: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(
            f"Unsupported input extension '{path.suffix}'. "
            f"Supported extensions: {supported}"
        )

    return path.resolve()


def _count_pages(input_path: Path) -> int:
    if input_path.suffix.lower() == ".pdf":
        page_count = len(PdfReader(str(input_path)).pages)
    else:
        with Image.open(input_path) as image:
            page_count = int(getattr(image, "n_frames", 1))
    if page_count < 1:
        raise ValueError(f"Input contains no pages: {input_path}")
    return page_count


def _document_name(input_path: Path) -> str:
    name = re.sub(r"[^\w.-]+", "_", input_path.stem, flags=re.UNICODE)
    name = name.strip(". _")[:120].rstrip(". ")
    if not name:
        raise ValueError(f"Cannot derive a safe document name from {input_path}")
    return name


def _plain_text_from_json(json_path: Path) -> str:
    """Extract ordered text blocks from PaddleOCR-VL JSON without Markdown syntax."""
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Could not read OCR JSON {json_path}: {exc}") from exc

    blocks = payload.get("parsing_res_list") if isinstance(payload, dict) else None
    if not isinstance(blocks, list):
        raise RuntimeError(f"OCR JSON has no parsing_res_list: {json_path}")

    indexed_blocks = [
        (index, block) for index, block in enumerate(blocks) if isinstance(block, dict)
    ]
    ordered_blocks = sorted(
        indexed_blocks,
        key=lambda item: (
            item[1].get("block_order") is None,
            item[1].get("block_order")
            if isinstance(item[1].get("block_order"), (int, float))
            else item[0],
            item[0],
        ),
    )
    text_blocks: list[str] = []
    for _, block in ordered_blocks:
        if str(block.get("block_label", "")).lower() in {"image", "header_image"}:
            continue
        content = block.get("block_content")
        if isinstance(content, str) and content.strip():
            text_blocks.append(content.strip())
    return "\n\n".join(text_blocks)


def _export_page(result: Any, page_number: int, staging_dir: Path) -> list[Path]:
    page_name = f"page_{page_number:03d}"
    page_staging_dir = staging_dir / f".{page_name}"
    page_staging_dir.mkdir()

    result.save_to_json(save_path=str(page_staging_dir))
    result.save_to_markdown(save_path=str(page_staging_dir))

    json_files = list(page_staging_dir.rglob("*.json"))
    markdown_files = list(page_staging_dir.rglob("*.md"))
    if len(json_files) != 1 or len(markdown_files) != 1:
        raise RuntimeError(
            f"PaddleOCR-VL export for {page_name} produced "
            f"{len(json_files)} JSON and {len(markdown_files)} Markdown files; "
            "expected one of each."
        )

    json_file = json_files[0]
    markdown_file = markdown_files[0]
    json_target = staging_dir / f"{page_name}.json"
    markdown_target = staging_dir / f"{page_name}.md"
    text_target = staging_dir / f"{page_name}.txt"
    shutil.move(str(json_file), str(json_target))

    markdown = markdown_file.read_text(encoding="utf-8")
    markdown_file.unlink()
    exported_assets: list[Path] = []
    for item in list(page_staging_dir.iterdir()):
        asset_name = f"{page_name}_{item.name}"
        asset_target = staging_dir / asset_name
        shutil.move(str(item), str(asset_target))
        markdown = markdown.replace(f"{item.name}/", f"{asset_name}/")
        markdown = markdown.replace(f"({item.name})", f"({asset_name})")
        if asset_target.is_dir():
            exported_assets.extend(
                path for path in asset_target.rglob("*") if path.is_file()
            )
        else:
            exported_assets.append(asset_target)

    markdown_target.write_text(markdown, encoding="utf-8")
    plain_text = _plain_text_from_json(json_target)
    text_target.write_text(plain_text, encoding="utf-8")
    shutil.rmtree(page_staging_dir)
    return [json_target, markdown_target, text_target, *exported_assets]


def process_document(
    input_path: str | Path,
    output_root: str | Path = "data/raw",
    engine: OCREngine | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Recognize a file and emit each durable raw page with progress updates."""
    source = _validate_input(input_path)
    document_name = _document_name(source)
    try:
        page_count = _count_pages(source)
    except Exception as exc:
        raise RuntimeError(f"Could not count pages in {source}: {exc}") from exc

    output_root_path = Path(output_root).expanduser()
    output_root_path.mkdir(parents=True, exist_ok=True)
    document_dir = output_root_path / document_name
    if document_dir.exists():
        raise FileExistsError(
            f"Output folder already exists; refusing to overwrite: {document_dir}"
        )
    try:
        document_dir.mkdir()
    except FileExistsError:
        raise FileExistsError(
            f"Output folder already exists; refusing to overwrite: {document_dir}"
        ) from None

    output_files: list[Path] = []
    pages: list[dict[str, Any]] = []
    ocr_engine: OCREngine | None = None
    try:
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "processing_started",
                    "document_name": document_name,
                    "completed": 0,
                    "total": page_count,
                    "stage": "model_loading",
                    "message": "Đang nạp PaddleOCR-VL và các model phụ trợ.",
                }
            )
        ocr_engine = engine if engine is not None else PaddleOCRVLEngine()
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "stage_changed",
                    "stage": "document_preparation",
                    "message": "Đã nạp model; đang chuẩn bị luồng nhận dạng tài liệu.",
                }
            )
        results = iter(ocr_engine.predict(source))
        page_number = 0
        for next_page in range(1, page_count + 1):
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "page_started",
                        "stage": "page_inference",
                        "message": f"PaddleOCR-VL đang nhận dạng trang {next_page}/{page_count}.",
                        "page_number": next_page,
                    }
                )
            try:
                result = next(results)
            except StopIteration:
                break
            page_number = next_page
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "stage_changed",
                        "stage": "page_export",
                        "message": f"Đã nhận dạng trang {page_number}; đang ghi Markdown, JSON và hình cắt.",
                        "page_number": page_number,
                    }
                )
            with tempfile.TemporaryDirectory(
                prefix=f".{document_name}-{page_number:03d}-",
                dir=output_root_path,
            ) as temporary_dir:
                staging_dir = Path(temporary_dir)
                staged_files = _export_page(result, page_number, staging_dir)
                final_files: list[Path] = []
                for staged_file in staged_files:
                    final_file = document_dir / staged_file.relative_to(staging_dir)
                    final_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(staged_file), str(final_file))
                    final_files.append(final_file)

            page_number_name = f"page_{page_number:03d}"
            text_path = document_dir / f"{page_number_name}.txt"
            markdown_path = document_dir / f"{page_number_name}.md"
            page_record = {
                "page_id": page_number_name,
                "page_number": page_number,
                "text": text_path.read_text(encoding="utf-8"),
                "text_path": str(text_path),
                "json_path": str(document_dir / f"{page_number_name}.json"),
                "markdown_path": str(markdown_path),
            }
            pages.append(page_record)
            output_files.extend(final_files)
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "page_completed",
                        "document_name": document_name,
                        "completed": page_number,
                        "total": page_count,
                        "page_number": page_number,
                    }
                )

        if page_number == page_count:
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "stage_changed",
                        "stage": "result_validation",
                        "message": "Đang kiểm tra số trang PaddleOCR-VL đã trả về.",
                    }
                )
            try:
                next(results)
            except StopIteration:
                pass
            else:
                raise RuntimeError(
                    f"PaddleOCR-VL returned more than {page_count} pages "
                    f"for {source}"
                )

        if len(pages) != page_count:
            raise RuntimeError(
                f"PaddleOCR-VL returned {len(pages)} of {page_count} expected "
                f"pages for {source}"
            )
    except Exception as exc:
        if not pages:
            try:
                document_dir.rmdir()
            except OSError:
                pass
        raise RuntimeError(
            f"PaddleOCR-VL failed for {source} after {len(pages)} of "
            f"{page_count} pages: {exc}"
        ) from exc
    finally:
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "stage_changed",
                    "stage": "model_release",
                    "message": "Đang đóng model OCR và thu hồi tài nguyên.",
                }
            )
        close_engine = getattr(ocr_engine, "close", None)
        if callable(close_engine):
            try:
                close_engine()
            except Exception:
                logging.exception("Failed to close PaddleOCR-VL inference models")
        ocr_engine = None
        gc.collect()

    return {
        "document_name": document_name,
        "output_dir": str(document_dir),
        "page_count": page_count,
        "pages": pages,
        "outputs": [str(path) for path in output_files],
    }
