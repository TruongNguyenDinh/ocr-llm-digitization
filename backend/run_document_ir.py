import json
import sys
from pathlib import Path

from backend.llm.reading_order import (
    reorder_blocks,
)

from backend.llm.layout import (
    merge_blocks,
)

from backend.llm.document_ir import (
    build_document,
    build_page,
)


def main():

    if len(sys.argv) != 3:
        print(
            "Usage: "
            "python -m backend.run_document_ir "
            "<input> <output>"
        )
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    with open(
        input_path,
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    pages = []

    for page in data["pages"]:

        ordered = reorder_blocks(
            page["blocks"]
        )

        blocks = merge_blocks(
            ordered
        )

        pages.append(
            build_page(
                page,
                blocks,
            )
        )

    result = build_document(
        data,
        pages,
    )

    output = Path(
        output_path
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        output,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2,
        )

    total_elements = sum(
        len(page["elements"])
        for page in pages
    )

    print(
        f"Pages: {len(pages)}"
    )

    print(
        f"Elements: {total_elements}"
    )

    print(
        f"Output: {output_path}"
    )


if __name__ == "__main__":
    main()