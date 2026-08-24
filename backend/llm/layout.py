from typing import List, Dict


def get_bbox(block: Dict):
    points = block.get("bbox")

    if not points or len(points) != 4:
        return None

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]

    return {
        "x1": min(xs),
        "y1": min(ys),
        "x2": max(xs),
        "y2": max(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }


def horizontal_overlap(
    first: Dict,
    second: Dict,
):
    first_box = get_bbox(first)
    second_box = get_bbox(second)

    if not first_box or not second_box:
        return 0.0

    overlap_start = max(
        first_box["x1"],
        second_box["x1"],
    )

    overlap_end = min(
        first_box["x2"],
        second_box["x2"],
    )

    overlap = max(
        0,
        overlap_end - overlap_start,
    )

    reference_width = min(
        first_box["width"],
        second_box["width"],
    )

    if reference_width <= 0:
        return 0.0

    return overlap / reference_width


def calculate_line_gap(
    blocks: List[Dict],
):
    gaps = []

    previous_block = None

    for block in blocks:

        if block.get("type") != "paragraph":
            continue

        current_box = get_bbox(block)

        if not current_box:
            continue

        if previous_block is not None:

            previous_box = get_bbox(
                previous_block
            )

            if previous_box:

                gap = max(
                    0,
                    current_box["y1"]
                    - previous_box["y2"],
                )

                if gap > 0:
                    gaps.append(gap)

        previous_block = block

    if not gaps:
        return 20.0

    gaps.sort()

    half = max(
        1,
        len(gaps) // 2,
    )

    small_gaps = gaps[:half]

    return small_gaps[
        len(small_gaps) // 2
    ]


def should_merge(
    current: Dict,
    previous: Dict,
    line_gap: float,
    gap_ratio: float = 1.35,
    min_horizontal_overlap: float = 0.25,
):
    if current.get("type") != "paragraph":
        return False

    if previous.get("type") != "paragraph":
        return False

    current_box = get_bbox(current)
    previous_box = get_bbox(previous)

    if not current_box or not previous_box:
        return False

    vertical_gap = max(
        0,
        current_box["y1"]
        - previous_box["y2"],
    )

    if vertical_gap > line_gap * gap_ratio:
        return False

    overlap = horizontal_overlap(
        previous,
        current,
    )

    if overlap < min_horizontal_overlap:
        return False

    return True


def merge_bbox(
    first: Dict,
    second: Dict,
):
    first_box = get_bbox(first)
    second_box = get_bbox(second)

    x1 = min(
        first_box["x1"],
        second_box["x1"],
    )

    y1 = min(
        first_box["y1"],
        second_box["y1"],
    )

    x2 = max(
        first_box["x2"],
        second_box["x2"],
    )

    y2 = max(
        first_box["y2"],
        second_box["y2"],
    )

    return [
        [x1, y1],
        [x2, y1],
        [x2, y2],
        [x1, y2],
    ]

def merge_blocks(
    blocks: List[Dict],
) -> List[Dict]:

    if not blocks:
        return []

    line_gap = calculate_line_gap(blocks)

    result = []

    current = blocks[0].copy()
    last_block = blocks[0]

    # Giữ lại các OCR line gốc
    current["lines"] = [
        {
            "text": blocks[0].get("text", "").strip(),
            "bbox": blocks[0].get("bbox"),
            "confidence": blocks[0].get(
                "confidence",
                1.0,
            ),
        }
    ]

    for block in blocks[1:]:

        if should_merge(
            block,
            last_block,
            line_gap=line_gap,
        ):
            current["text"] = (
                current["text"].rstrip()
                + " "
                + block["text"].lstrip()
            )

            current["bbox"] = merge_bbox(
                current,
                block,
            )

            current["confidence"] = min(
                current.get(
                    "confidence",
                    1.0,
                ),
                block.get(
                    "confidence",
                    1.0,
                ),
            )

            current["lines"].append(
                {
                    "text": block.get(
                        "text",
                        "",
                    ).strip(),
                    "bbox": block.get(
                        "bbox"
                    ),
                    "confidence": block.get(
                        "confidence",
                        1.0,
                    ),
                }
            )

            last_block = block

        else:
            result.append(current)

            current = block.copy()

            current["lines"] = [
                {
                    "text": block.get(
                        "text",
                        "",
                    ).strip(),
                    "bbox": block.get(
                        "bbox"
                    ),
                    "confidence": block.get(
                        "confidence",
                        1.0,
                    ),
                }
            ]

            last_block = block

    result.append(current)

    return result