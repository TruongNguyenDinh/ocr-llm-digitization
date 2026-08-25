from .schemas import OCRBlock


def sort_reading_order(
    blocks: list[OCRBlock],
) -> list[OCRBlock]:

    if not blocks:
        return []

    # --------------------------------------------------
    # OCR blocks are already line-level blocks.
    #
    # Therefore reading order is simply:
    #
    #   top -> bottom
    #   left -> right
    #
    # Do NOT detect columns here.
    # Do NOT merge lines here.
    # Paragraph merging is handled later.
    # --------------------------------------------------

    ordered = sorted(
        blocks,
        key=lambda block: (
            block.y_min,
            block.x_min,
        ),
    )

    # --------------------------------------------------
    # Assign reading order
    # --------------------------------------------------

    for index, block in enumerate(
        ordered,
        start=1,
    ):

        block.reading_order = index

    return ordered