from pathlib import Path

from paddleocr import PaddleOCR


class OCREngine:

    def __init__(self):

        self.ocr = PaddleOCR(
            lang="vi",
        )

    def process(
        self,
        image_path: str | Path,
    ):

        image_path = str(image_path)

        result = self.ocr.predict(
            image_path
        )

        return result