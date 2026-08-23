from pathlib import Path
import json

import cv2

from .loader import (
    validate_file,
    is_pdf,
    is_image,
)

from .pdf_converter import pdf_to_images
from .grayscale import to_grayscale
from .deskew import deskew
from .enhancement import enhance_contrast
from .resize import resize_if_needed


def process_image(
    image_path: Path,
    output_path: Path,
) -> dict:

    image = cv2.imread(
        str(image_path),
        cv2.IMREAD_COLOR,
    )

    if image is None:
        raise ValueError(
            f"Không thể đọc ảnh: {image_path}"
        )

    original_height, original_width = image.shape[:2]

    # 1. Grayscale
    image = to_grayscale(image)

    # 2. Deskew
    image, angle = deskew(image)

    # 3. Contrast enhancement
    image = enhance_contrast(image)

    # 4. Resize
    image = resize_if_needed(image)

    processed_height, processed_width = image.shape[:2]

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    cv2.imwrite(
        str(output_path),
        image,
    )

    return {
        "original_size": [
            original_width,
            original_height,
        ],
        "processed_size": [
            processed_width,
            processed_height,
        ],
        "deskew_angle": angle,
        "operations": [
            "grayscale",
            "deskew",
            "clahe",
            "resize",
        ],
    }


def process_document(
    input_path: str,
    output_dir: str,
):

    input_path = validate_file(input_path)

    output_dir = Path(output_dir)

    document_name = input_path.stem

    document_output_dir = (
        output_dir / document_name
    )

    document_output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # PDF
    if is_pdf(input_path):

        page_paths = pdf_to_images(
            input_path,
            document_output_dir,
        )

    # Image
    elif is_image(input_path):

        page_path = (
            document_output_dir
            / "page_001.png"
        )

        image = cv2.imread(
            str(input_path),
            cv2.IMREAD_COLOR,
        )

        cv2.imwrite(
            str(page_path),
            image,
        )

        page_paths = [page_path]

    else:
        raise ValueError(
            "Unsupported document type"
        )

    metadata = {
        "document": input_path.name,
        "pages": [],
    }

    processed_pages = []

    for page_path in page_paths:

        processed_path = (
            document_output_dir
            / f"processed_{page_path.name}"
        )

        page_metadata = process_image(
            page_path,
            processed_path,
        )

        page_metadata["page"] = (
            len(processed_pages) + 1
        )

        processed_pages.append(
            processed_path
        )

        metadata["pages"].append(
            page_metadata
        )

    metadata_path = (
        document_output_dir
        / "metadata.json"
    )

    with open(
        metadata_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            metadata,
            file,
            ensure_ascii=False,
            indent=4,
        )

    return processed_pages