import re

from .schemas import OCRBlock


MIN_CONFIDENCE = 0.50


def normalize_text(text: str) -> str:
    text = text.strip()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text


def normalize_result(result) -> list[OCRBlock]:

    blocks = []

    for page_result in result:

        texts = page_result["rec_texts"]
        scores = page_result["rec_scores"]
        boxes = page_result["rec_polys"]

        for text, score, box in zip(
            texts,
            scores,
            boxes,
        ):

            text = normalize_text(str(text))
            score = float(score)

            if not text:
                continue

            if score < MIN_CONFIDENCE:
                continue

            blocks.append(
                OCRBlock(
                    text=text,
                    confidence=score,
                    bbox=box.tolist(),
                )
            )

    return blocks