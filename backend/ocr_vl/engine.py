import logging
from pathlib import Path
from typing import Any, Iterable


# PaddleX currently defaults PaddleOCR-VL to 8192 generated tokens. Use a very
# high ceiling so inference normally ends on the model's EOS token instead.
# This is the largest practical signed 32-bit limit accepted by its generator.
UNLIMITED_MAX_NEW_TOKENS = 2_147_483_647


def _warmup_cuda_embedding() -> None:
    """Load the BF16 embedding kernel before allocating OCR model weights.

    On WSL, loading it lazily at the first VLM forward has intermittently
    stalled inside cuLibraryGetModule with almost all VRAM already occupied.
    Synchronize here so initialization finishes before PaddleX starts workers.
    """
    import paddle

    paddle.set_device("gpu:0")
    token_ids = paddle.to_tensor([0, 1], dtype="int64")
    weights = paddle.ones([2, 8], dtype="bfloat16")
    paddle.nn.functional.embedding(token_ids, weights)
    paddle.device.cuda.synchronize()
    logging.getLogger(__name__).info("CUDA BF16 embedding warm-up completed.")


class PaddleOCRVLEngine:
    """Thin reusable adapter around PaddleOCR-VL."""

    def __init__(self, pipeline: Any | None = None) -> None:
        if pipeline is None:
            try:
                _warmup_cuda_embedding()
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
                device="gpu:0",
            )

        self.pipeline = pipeline

    def predict(self, input_path: str | Path) -> Iterable[Any]:
        """Yield native PaddleOCR-VL results as each page finishes."""
        predict_iter = getattr(self.pipeline, "predict_iter", None)
        if predict_iter is None:
            # Keep compatibility with injected test/custom pipelines that only
            # implement the public predict() method.
            yield from self.pipeline.predict(input=str(input_path))
            return

        yield from predict_iter(
            input=str(input_path),
            max_new_tokens=UNLIMITED_MAX_NEW_TOKENS,
        )

    def close(self) -> None:
        """Close PaddleX models and their inference runners."""
        close = getattr(self.pipeline, "close", None)
        if callable(close):
            close()
