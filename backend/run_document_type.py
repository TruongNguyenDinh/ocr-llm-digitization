import json
import sys

from backend.llm.document_type import (
    DocumentTypeDetector,
)


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python -m backend.run_document_type "
            "<input_json> <output_json>"
        )
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    detector = DocumentTypeDetector()

    result = detector.detect(
        input_path
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
        f"Document type: "
        f"{result['document_type']}"
    )

    print(
        f"Confidence: "
        f"{result['confidence']}"
    )

    print(
        f"Output: {output_path}"
    )


if __name__ == "__main__":
    main()