from typing import Dict, List
from statistics import median


FLOW_TYPES = {
    "title",
    "heading",
    "subheading",
    "salutation",
    "paragraph",
    "closing",
    "caption",
    "list_item",
}

FLOATING_TYPES = {
    "signature",
    "visual_candidate",
    "image",
    "logo",
    "stamp",
    "table",
    "figure",
}


# ============================================================
# GEOMETRY
# ============================================================

def bbox_rect(bbox):
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]

    return (
        min(xs),
        min(ys),
        max(xs),
        max(ys),
    )


def get_x(element):
    bbox = element.get("bbox")

    if not bbox:
        return 0

    return min(
        p[0]
        for p in bbox
    )


def get_y(element):
    bbox = element.get("bbox")

    if not bbox:
        return 0

    return min(
        p[1]
        for p in bbox
    )


def get_right(element):
    bbox = element.get("bbox")

    if not bbox:
        return 0

    return max(
        p[0]
        for p in bbox
    )


def get_top(element):
    bbox = element.get("bbox")

    if not bbox:
        return 0

    return min(
        p[1]
        for p in bbox
    )


def get_bottom(element):
    bbox = element.get("bbox")

    if not bbox:
        return 0

    return max(
        p[1]
        for p in bbox
    )


def bbox_height(bbox):
    if not bbox:
        return 0

    ys = [
        p[1]
        for p in bbox
    ]

    return max(ys) - min(ys)


def union_bbox(
    bbox1,
    bbox2,
):
    """
    Combine two bounding boxes.
    """

    points = []

    if bbox1:
        points.extend(
            bbox1
        )

    if bbox2:
        points.extend(
            bbox2
        )

    if not points:
        return None

    xs = [
        p[0]
        for p in points
    ]

    ys = [
        p[1]
        for p in points
    ]

    return [
        [min(xs), min(ys)],
        [max(xs), min(ys)],
        [max(xs), max(ys)],
        [min(xs), max(ys)],
    ]


# ============================================================
# NORMALIZE UNKNOWN
# ============================================================

def normalize_unknown(
    block: Dict,
):
    """
    Low-confidence unknown OCR block
    becomes visual_candidate.
    """

    block = dict(block)

    element_type = block.get(
        "type",
        "unknown",
    )

    confidence = block.get(
        "confidence",
        1.0,
    )

    if (
        element_type == "unknown"
        and confidence < 0.90
    ):
        block["type"] = (
            "visual_candidate"
        )

    return block


# ============================================================
# GAP ANALYSIS
# ============================================================

def get_center_y(element):
    bbox = element.get("bbox")

    if not bbox:
        return None

    ys = [
        p[1]
        for p in bbox
    ]

    return (
        min(ys) + max(ys)
    ) / 2


def calculate_line_gaps(
    blocks: List[Dict],
):
    """
    Calculate vertical distance between
    the centers of consecutive OCR blocks.

    We intentionally use center-Y instead of:

        current_top - previous_bottom

    because OCR quadrilaterals can be rotated,
    causing bounding boxes to overlap vertically.
    """

    gaps = []

    previous = None

    for block in blocks:

        if not block.get("bbox"):
            continue

        if previous is not None:

            previous_center = get_center_y(
                previous
            )

            current_center = get_center_y(
                block
            )

            if (
                previous_center is not None
                and current_center is not None
            ):

                gap = (
                    current_center
                    - previous_center
                )

                gaps.append(
                    {
                        "previous": previous,
                        "current": block,
                        "gap": gap,
                    }
                )

        previous = block

    return gaps


def detect_paragraph_breaks(
    blocks: List[Dict],
):
    """
    Detect paragraph boundaries using
    vertical center-to-center gap outliers.
    """

    gap_data = calculate_line_gaps(
        blocks
    )

    if not gap_data:
        return set()

    positive_gaps = [
        item["gap"]
        for item in gap_data
        if item["gap"] > 0
    ]

    if not positive_gaps:
        return set()

    baseline = median(
        positive_gaps
    )

    print(
        "\n[LAYOUT] line center gaps:"
    )

    for index, item in enumerate(
        gap_data
    ):

        print(
            f"  {index:02d}: "
            f"{item['gap']:.2f}"
        )

    print(
        f"[LAYOUT] baseline median: "
        f"{baseline:.2f}"
    )

    breaks = set()

    for index, item in enumerate(
        gap_data
    ):

        gap = item["gap"]

        if gap <= 0:
            continue

        ratio = (
            gap / baseline
        )

        # Gap lớn bất thường
        if ratio >= 1.6:

            breaks.add(
                index
            )

            print(
                f"[LAYOUT] BREAK "
                f"at gap {index}: "
                f"{gap:.2f} "
                f"(ratio={ratio:.2f})"
            )

    return breaks


# ============================================================
# SEMANTIC MERGE
# ============================================================

def merge_semantic_blocks(
    blocks: List[Dict],
):
    """
    Merge OCR line blocks into semantic blocks.

    Paragraph boundaries are determined from
    vertical-gap outliers.
    """

    normalized_blocks = []

    # --------------------------------------------------------
    # Normalize blocks
    # --------------------------------------------------------

    for raw_block in blocks:

        block = normalize_unknown(
            raw_block
        )

        text = block.get(
            "corrected_text",
            block.get(
                "text",
                "",
            ),
        ).strip()

        if not text:
            continue

        block = dict(
            block
        )

        block["text"] = text

        normalized_blocks.append(
            block
        )

    if not normalized_blocks:
        return []

    # --------------------------------------------------------
    # Detect paragraph boundaries
    # --------------------------------------------------------

    paragraph_breaks = (
        detect_paragraph_breaks(
            normalized_blocks
        )
    )

    result = []

    current = None

    # --------------------------------------------------------
    # Merge
    # --------------------------------------------------------

    for index, block in enumerate(
        normalized_blocks
    ):

        block_type = block.get(
            "type",
            "unknown",
        )

        # ----------------------------------------------------
        # First block
        # ----------------------------------------------------

        if current is None:

            current = dict(
                block
            )

            continue

        current_type = current.get(
            "type",
            "unknown",
        )

        # ----------------------------------------------------
        # Paragraph + Paragraph
        # ----------------------------------------------------

        if (
            current_type == "paragraph"
            and block_type == "paragraph"
        ):

            # Gap index:
            #
            # block[0] -> block[1] = gap 0
            # block[1] -> block[2] = gap 1
            #
            # Therefore current block index
            # uses index - 1.

            if (
                index - 1
                in paragraph_breaks
            ):

                # New paragraph
                result.append(
                    current
                )

                current = dict(
                    block
                )

            else:

                # Same paragraph
                current["text"] = (
                    current["text"]
                    + " "
                    + block["text"]
                )

                current["bbox"] = union_bbox(
                    current.get(
                        "bbox"
                    ),
                    block.get(
                        "bbox"
                    ),
                )

            continue

        # ----------------------------------------------------
        # Different semantic type
        # ----------------------------------------------------

        result.append(
            current
        )

        current = dict(
            block
        )

    # --------------------------------------------------------
    # Last block
    # --------------------------------------------------------

    if current is not None:

        result.append(
            current
        )

    # --------------------------------------------------------
    # Rebuild order
    # --------------------------------------------------------

    for index, element in enumerate(
        result,
        start=1,
    ):

        element["order"] = index

    return result


# ============================================================
# CLASSIFICATION
# ============================================================

def classify_elements(
    elements: List[Dict],
):
    """
    Separate semantic elements into:

        flow
        floating
    """

    flow = []

    floating = []

    for element in elements:

        element_type = element.get(
            "type",
            "unknown",
        )

        if element_type in FLOW_TYPES:

            flow.append(
                element
            )

        elif element_type in FLOATING_TYPES:

            floating.append(
                element
            )

        else:

            floating.append(
                element
            )

    return flow, floating


# ============================================================
# TEXT COLUMN
# ============================================================

def infer_text_column(
    flow_elements: List[Dict],
):
    """
    Infer main text column.

    Paragraphs determine X and width.

    Y is only metadata.
    It does NOT control HTML layout.
    """

    paragraphs = [
        e
        for e in flow_elements
        if (
            e.get("type") == "paragraph"
            and e.get("bbox")
        )
    ]

    valid_flow = [
        e
        for e in flow_elements
        if e.get("bbox")
    ]

    # --------------------------------------------------------
    # X / WIDTH
    # --------------------------------------------------------

    if paragraphs:

        left = min(
            get_x(e)
            for e in paragraphs
        )

        right = max(
            get_right(e)
            for e in paragraphs
        )

    elif valid_flow:

        left = min(
            get_x(e)
            for e in valid_flow
        )

        right = max(
            get_right(e)
            for e in valid_flow
        )

    else:

        return {
            "x": 0,
            "y": 0,
            "width": 0,
        }

    # --------------------------------------------------------
    # Y
    # --------------------------------------------------------

    if valid_flow:

        top = min(
            get_y(e)
            for e in valid_flow
        )

    else:

        top = 0

    return {
        "x": left,
        "y": top,
        "width": right - left,
    }


# ============================================================
# ALIGNMENT
# ============================================================

def infer_alignment(
    element,
    column,
    tolerance=40,
):
    """
    Infer semantic horizontal alignment.
    """

    bbox = element.get(
        "bbox"
    )

    if not bbox:
        return "left"

    x1, _, x2, _ = bbox_rect(
        bbox
    )

    column_x = column["x"]

    column_right = (
        column["x"]
        + column["width"]
    )

    element_center = (
        x1 + x2
    ) / 2

    column_center = (
        column_x
        + column["width"] / 2
    )

    # --------------------------------------------------------
    # LEFT
    # --------------------------------------------------------

    if abs(
        x1 - column_x
    ) <= tolerance:

        return "left"

    # --------------------------------------------------------
    # RIGHT
    # --------------------------------------------------------

    if abs(
        x2 - column_right
    ) <= tolerance:

        return "right"

    # --------------------------------------------------------
    # CENTER
    # --------------------------------------------------------

    if abs(
        element_center
        - column_center
    ) <= tolerance:

        return "center"

    return "left"


# ============================================================
# INDENTATION
# ============================================================

def infer_indentation(
    element,
    column,
    tolerance=40,
):
    """
    Detect intentional paragraph indentation.

    Small differences are ignored.

    Large differences become indentation.
    """

    if element.get(
        "type"
    ) != "paragraph":

        return 0

    x = get_x(
        element
    )

    base_x = column[
        "x"
    ]

    difference = (
        x - base_x
    )

    if abs(
        difference
    ) <= tolerance:

        return 0

    return max(
        0,
        difference,
    )


# ============================================================
# BUILD FLOW ELEMENT
# ============================================================

def build_flow_element(
    element,
    column,
):
    """
    Convert semantic block into
    layout representation.

    Absolute Y is intentionally removed.
    """

    element_type = element.get(
        "type",
        "unknown",
    )

    result = {
        "order": element.get(
            "order"
        ),
        "type": element_type,
        "text": element.get(
            "text",
            "",
        ),
    }

    # --------------------------------------------------------
    # PARAGRAPH
    # --------------------------------------------------------

    if element_type == "paragraph":

        result["indent"] = (
            infer_indentation(
                element,
                column,
            )
        )

        result["alignment"] = (
            "left"
        )

    # --------------------------------------------------------
    # OTHER FLOW
    # --------------------------------------------------------

    else:

        result["alignment"] = (
            infer_alignment(
                element,
                column,
            )
        )

    return result


# ============================================================
# BUILD FLOATING
# ============================================================

def build_floating_element(
    element,
):
    """
    Floating elements keep original bbox.
    """

    return {
        "order": element.get(
            "order"
        ),
        "type": element.get(
            "type",
            "unknown",
        ),
        "text": element.get(
            "text",
            "",
        ),
        "bbox": element.get(
            "bbox"
        ),
        "confidence": element.get(
            "confidence",
            1.0,
        ),
    }


# ============================================================
# PAGE LAYOUT
# ============================================================

def infer_page_layout(
    page: Dict,
):
    """
    Pipeline:

        OCR
          ↓
        Reading Order
          ↓
        Semantic Merge
          ↓
        Flow / Floating
          ↓
        Layout IR
    """

    # --------------------------------------------------------
    # INPUT
    # --------------------------------------------------------

    blocks = page.get(
        "blocks",
        page.get(
            "elements",
            [],
        ),
    )

    # --------------------------------------------------------
    # READING ORDER
    # --------------------------------------------------------

    from .reading_order import (
        reorder_blocks,
    )

    blocks = reorder_blocks(
        blocks
    )

    # --------------------------------------------------------
    # SEMANTIC MERGE
    # --------------------------------------------------------

    elements = merge_semantic_blocks(
        blocks
    )

    # --------------------------------------------------------
    # CLASSIFY
    # --------------------------------------------------------

    flow, floating = classify_elements(
        elements
    )

    # --------------------------------------------------------
    # TEXT COLUMN
    # --------------------------------------------------------

    column = infer_text_column(
        flow
    )

    # --------------------------------------------------------
    # ORDER
    # --------------------------------------------------------

    flow.sort(
        key=lambda e: e.get(
            "order",
            0,
        )
    )

    floating.sort(
        key=lambda e: e.get(
            "order",
            0,
        )
    )

    # --------------------------------------------------------
    # BUILD FLOW
    # --------------------------------------------------------

    flow_elements = []

    for index, element in enumerate(
        flow,
        start=1,
    ):

        result = build_flow_element(
            element,
            column,
        )

        result["order"] = index

        flow_elements.append(
            result
        )

    # --------------------------------------------------------
    # BUILD FLOATING
    # --------------------------------------------------------

    floating_elements = []

    for index, element in enumerate(
        floating,
        start=1,
    ):

        result = build_floating_element(
            element
        )

        result["order"] = index

        floating_elements.append(
            result
        )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    return {
        "mode": "flow",

        "content": {
            "x": column["x"],
            "y": column["y"],
            "width": column["width"],
        },

        "flow": flow_elements,

        "floating": floating_elements,
    }


# ============================================================
# DOCUMENT LAYOUT
# ============================================================

def infer_document_layout(
    data: Dict,
):
    """
    Build complete Layout IR.
    """

    result = {
        "document_type": data.get(
            "document_type",
            "unknown",
        ),
        "pages": [],
    }

    for page in data.get(
        "pages",
        [],
    ):

        layout = infer_page_layout(
            page
        )

        result["pages"].append(
            {
                "page": page.get(
                    "page"
                ),
                "width": page.get(
                    "width"
                ),
                "height": page.get(
                    "height"
                ),
                "source_image": page.get(
                    "source_image"
                ),
                "layout": layout,
            }
        )

    return result