from pathlib import Path


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tiff",
    ".webp",
}

SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | {".pdf"}


def validate_file(file_path: str) -> Path:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"File không tồn tại: {file_path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Không phải file: {file_path}"
        )

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Định dạng không được hỗ trợ: {path.suffix}"
        )

    return path


def is_pdf(file_path: Path) -> bool:
    return file_path.suffix.lower() == ".pdf"


def is_image(file_path: Path) -> bool:
    return file_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS