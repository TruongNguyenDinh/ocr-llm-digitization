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
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
        "center_y": (min(ys) + max(ys)) / 2,
    }


def reorder_blocks(
    blocks: List[Dict],
    y_tolerance_ratio: float = 0.5,
) -> List[Dict]:

    if not blocks:
        return []

    enriched = []

    for block in blocks:
        bbox = get_bbox(block)

        if bbox is None:
            continue

        item = block.copy()
        item["_bbox"] = bbox

        enriched.append(item)

    lines = []

    for block in enriched:
        bbox = block["_bbox"]

        best_line = None
        best_distance = float("inf")

        for line in lines:
            distance = abs(
                bbox["center_y"] -
                line["center_y"]
            )

            tolerance = max(
                bbox["height"],
                line["height"],
            ) * y_tolerance_ratio

            if distance <= tolerance:
                if distance < best_distance:
                    best_distance = distance
                    best_line = line

        if best_line is None:
            lines.append(
                {
                    "center_y": bbox["center_y"],
                    "height": bbox["height"],
                    "blocks": [block],
                }
            )
        else:
            best_line["blocks"].append(block)

            best_line["center_y"] = sum(
                item["_bbox"]["center_y"]
                for item in best_line["blocks"]
            ) / len(best_line["blocks"])

            best_line["height"] = max(
                item["_bbox"]["height"]
                for item in best_line["blocks"]
            )

    lines.sort(
        key=lambda line: line["center_y"]
    )

    result = []
    reading_order = 1

    for line in lines:

        line["blocks"].sort(
            key=lambda block:
            block["_bbox"]["x1"]
        )

        for block in line["blocks"]:

            block.pop("_bbox", None)

            block["reading_order"] = reading_order

            reading_order += 1

            result.append(block)

    return result