from typing import List, Dict


def get_bbox(block: Dict):

    points = block.get(
        "bbox"
    )

    if not points or len(points) != 4:
        return None

    xs = [
        p[0]
        for p in points
    ]

    ys = [
        p[1]
        for p in points
    ]

    return {
        "x1": min(xs),
        "y1": min(ys),
        "x2": max(xs),
        "y2": max(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
        "center_x": (
            min(xs) + max(xs)
        ) / 2,
        "center_y": (
            min(ys) + max(ys)
        ) / 2,
    }


def reorder_blocks(
    blocks: List[Dict],
) -> List[Dict]:

    if not blocks:
        return []

    # --------------------------------------------------
    # IMPORTANT
    #
    # OCR already calculated reading order.
    # Do not destroy it unnecessarily.
    # --------------------------------------------------

    has_reading_order = any(
        block.get("reading_order")
        is not None
        for block in blocks
    )

    if has_reading_order:

        ordered = sorted(
            blocks,
            key=lambda block: (
                block.get(
                    "reading_order",
                    10**9,
                )
            ),
        )

        return ordered

    # --------------------------------------------------
    # Fallback
    #
    # Only calculate reading order if OCR did not
    # provide one.
    # --------------------------------------------------

    enriched = []

    for block in blocks:

        bbox = get_bbox(
            block
        )

        if bbox is None:
            continue

        enriched.append(
            {
                "block": block,
                "bbox": bbox,
            }
        )

    if not enriched:
        return []

    # --------------------------------------------------
    # Build visual lines.
    # --------------------------------------------------

    lines = []

    for item in sorted(
        enriched,
        key=lambda item: (
            item["bbox"]["y1"],
            item["bbox"]["x1"],
        ),
    ):

        bbox = item["bbox"]

        best_line = None
        best_distance = float(
            "inf"
        )

        for line in lines:

            line_bbox = line["bbox"]

            overlap = max(
                0,
                min(
                    bbox["y2"],
                    line_bbox["y2"],
                )
                -
                max(
                    bbox["y1"],
                    line_bbox["y1"],
                ),
            )

            min_height = min(
                bbox["height"],
                line_bbox["height"],
            )

            if min_height <= 0:
                continue

            overlap_ratio = (
                overlap
                / min_height
            )

            center_distance = abs(
                bbox["center_y"]
                -
                line["center_y"]
            )

            tolerance = max(
                bbox["height"],
                line_bbox["height"],
            ) * 0.45

            if (
                overlap_ratio >= 0.35
                or center_distance <= tolerance
            ):

                if (
                    center_distance
                    < best_distance
                ):

                    best_distance = (
                        center_distance
                    )

                    best_line = line

        if best_line is None:

            lines.append(
                {
                    "blocks": [item],
                    "bbox": bbox,
                    "center_y": bbox[
                        "center_y"
                    ],
                }
            )

        else:

            best_line[
                "blocks"
            ].append(item)

            all_items = (
                best_line["blocks"]
            )

            best_line["bbox"] = {
                "y1": min(
                    x["bbox"]["y1"]
                    for x in all_items
                ),
                "y2": max(
                    x["bbox"]["y2"]
                    for x in all_items
                ),
            }

            best_line[
                "center_y"
            ] = sum(
                x["bbox"]["center_y"]
                for x in all_items
            ) / len(
                all_items
            )

    # --------------------------------------------------
    # Sort lines vertically.
    # --------------------------------------------------

    lines.sort(
        key=lambda line:
        line["center_y"]
    )

    # --------------------------------------------------
    # Sort blocks inside each line by X.
    # --------------------------------------------------

    result = []

    for line in lines:

        line["blocks"].sort(
            key=lambda item:
            item["bbox"]["x1"]
        )

        for item in line["blocks"]:

            block = item["block"]

            block["reading_order"] = (
                len(result) + 1
            )

            result.append(
                block
            )

    return result