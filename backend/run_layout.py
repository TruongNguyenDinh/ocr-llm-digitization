import json
import sys
from pathlib import Path

from .llm.layout_inference import (
    infer_document_layout,
)


def main():

    if len(sys.argv) != 3:

        print(
            "Usage: "
            "python -m backend.run_layout "
            "<input.json> <output.json>"
        )

        sys.exit(1)

    input_path = Path(
        sys.argv[1]
    )

    output_path = Path(
        sys.argv[2]
    )

    with open(
        input_path,
        encoding="utf-8",
    ) as f:

        data = json.load(f)

    result = infer_document_layout(
        data
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"Pages: {len(result['pages'])}"
    )

    for page in result["pages"]:

        layout = page["layout"]

        print(
            f"PAGE {page['page']}: "
            f"flow={len(layout['flow'])}, "
            f"floating={len(layout['floating'])}"
        )

        print(
            "Content:",
            layout["content"]
        )

    print(
        f"Output: {output_path}"
    )


if __name__ == "__main__":
    main()