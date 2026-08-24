from typing import List, Dict


def build_element(
    block: Dict,
    order: int,
):
    element_type = block.get(
        "type",
        "unknown",
    )

    confidence = block.get(
        "confidence",
        1.0,
    )

    text = block.get(
        "text",
        "",
    ).strip()

    # Unknown + confidence thấp
    # -> visual candidate
    if element_type == "unknown":
        if confidence < 0.90:
            element_type = "visual_candidate"

    element = {
        "order": order,
        "type": element_type,
        "text": text,
        "bbox": block.get("bbox"),
        "confidence": confidence,
        "source": "ocr",
    }

    # Giữ nguyên các OCR lines
    if "lines" in block:
        element["lines"] = block["lines"]

    # Metadata cho visual candidate
    if element_type == "visual_candidate":
        element["visual"] = {
            "status": "candidate",
            "kind": None,
        }

    return element


def build_page(
    page: Dict,
    blocks: List[Dict],
):
    elements = []

    for order, block in enumerate(
        blocks,
        start=1,
    ):
        elements.append(
            build_element(
                block,
                order,
            )
        )

    return {
        "page": page["page"],
        "width": page.get("width"),
        "height": page.get("height"),
        "source_image": page.get(
            "source_image"
        ),
        "elements": elements,
    }


def build_document(
    data: Dict,
    pages: List[Dict],
):
    return {
        "document_type": data.get(
            "document_type",
            "unknown",
        ),
        "pages": pages,
    }