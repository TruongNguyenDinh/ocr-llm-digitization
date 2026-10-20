from pathlib import Path
from typing import Any, Iterable


class PaddleOCRVLEngine:
    """Thin reusable adapter around PaddleOCR-VL."""

    def __init__(self, pipeline: Any | None = None) -> None:
        if pipeline is None:
            try:
                from paddleocr import PaddleOCRVL
            except ImportError as exc:
                raise RuntimeError(
                    'PaddleOCR-VL is unavailable. Install '
                    '"paddleocr[doc-parser]" and a compatible PaddlePaddle '
                    "inference runtime."
                ) from exc

            pipeline = PaddleOCRVL(
                use_doc_orientation_classify=True,
                use_doc_unwarping=True,
            )

        self.pipeline = pipeline

    def predict(self, input_path: str | Path) -> Iterable[Any]:
        """Yield native PaddleOCR-VL results in source page order."""
        yield from self.pipeline.predict(input=str(input_path))
