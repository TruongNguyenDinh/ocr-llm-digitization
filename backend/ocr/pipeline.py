import json
from pathlib import Path

from .engine import OCREngine
from .postprocess import normalize_result
from .reading_order import sort_reading_order


class OCRPipeline:

    def __init__(self):
        self.engine = OCREngine()

    def process_document(
        self,
        document_dir: str,
        output_path: str,
    ):

        document_dir = Path(
            document_dir
        )

        page_images = sorted(
            document_dir.glob(
                "processed_page_*.png"
            )
        )

        document_id = document_dir.name

        pages = []

        for page_number, image_path in enumerate(
            page_images,
            start=1,
        ):

            print(
                f"OCR page {page_number}: "
                f"{image_path.name}"
            )

            raw_result = self.engine.process(
                image_path
            )

            blocks = normalize_result(
                raw_result
            )

            blocks = sort_reading_order(
                blocks
            )

            pages.append(
                {
                    "page": page_number,
                    "source_image": str(
                        image_path
                    ),
                    "blocks": [
                        {
                            "text": block.text,
                            "confidence": block.confidence,
                            "bbox": block.bbox,
                            "reading_order": block.reading_order,
                        }
                        for block in blocks
                    ],
                }
            )

        output = {
            "document_id": document_id,
            "pages": pages,
        }

        output_path = Path(
            output_path
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                output,
                file,
                ensure_ascii=False,
                indent=4,
            )

        return output