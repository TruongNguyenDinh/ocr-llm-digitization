from .schemas import OCRBlock


def sort_reading_order(
    blocks: list[OCRBlock],
) -> list[OCRBlock]:

    if not blocks:
        return blocks

    # Estimate page width
    page_width = max(
        block.x_max
        for block in blocks
    )

    # Heuristic:
    # detect whether the document has multiple columns
    column_threshold = page_width * 0.45

    left_column = []
    right_column = []
    single_column = []

    for block in blocks:

        if block.center_x < column_threshold:
            left_column.append(block)

        else:
            right_column.append(block)

    # If the right side is almost empty,
    # treat document as single-column.
    if len(right_column) < len(blocks) * 0.15:

        single_column = sorted(
            blocks,
            key=lambda b: (
                b.y_min,
                b.x_min,
            ),
        )

        ordered = single_column

    else:

        left_column.sort(
            key=lambda b: (
                b.y_min,
                b.x_min,
            )
        )

        right_column.sort(
            key=lambda b: (
                b.y_min,
                b.x_min,
            )
        )

        ordered = (
            left_column
            + right_column
        )

    for index, block in enumerate(
        ordered,
        start=1,
    ):

        block.reading_order = index

    return ordered