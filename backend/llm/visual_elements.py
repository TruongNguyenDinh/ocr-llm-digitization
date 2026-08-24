from typing import List, Dict


def get_bbox(block: Dict):
    points = block.get("bbox")

    if not points or len(points) != 4:
        return None

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    return {
        "x1": min(xs),
        "y1": min(ys),
        "x2": max(xs),
        "y2": max(ys),
    }


def bbox_area(block: Dict):
    bbox = get_bbox(block)

    if not bbox:
        return 0

    return (
        bbox["x2"] - bbox["x1"]
    ) * (
        bbox["y2"] - bbox["y1"]
    )


def classify_visual_candidate(
    block: Dict,
):
    block_type = block.get(
        "type",
        "unknown",
    )

    text = block.get(
        "text",
        "",
    ).strip()

    confidence = block.get(
        "confidence",
        1.0,
    )

    bbox = get_bbox(block)

    if not bbox:
        return False

    width = bbox["x2"] - bbox["x1"]
    height = bbox["y2"] - bbox["y1"]

    area = width * height

    # Không coi paragraph / salutation / closing
    # là visual element.
    if block_type in {
        "paragraph",
        "salutation",
        "closing",
    }:
        return False

    # Signature vẫn là một semantic element,
    # chưa coi là image.
    if block_type == "signature":
        return False

    # Unknown với confidence thấp là candidate.
    if block_type == "unknown":
        if confidence < 0.90:
            return True

        # Text rất ngắn nhưng vùng bbox lớn
        # có thể là visual/decorative element.
        if len(text) <= 10 and area > 30000:
            return True

    return False


def detect_visual_candidates(
    blocks: List[Dict],
):
    candidates = []

    for block in blocks:

        if classify_visual_candidate(
            block
        ):
            item = {
                "type": "visual_candidate",
                "bbox": block.get("bbox"),
                "text": block.get(
                    "text",
                    "",
                ),
                "confidence": block.get(
                    "confidence",
                    1.0,
                ),
                "source": "ocr_unknown",
            }

            candidates.append(item)

    return candidates