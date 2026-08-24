import sys

from backend.llm.structure_pipeline import (
    StructurePipeline,
)


def main():

    if len(sys.argv) != 4:

        print(
            "Usage: python -m backend.run_structure "
            "<ocr_json> "
            "<document_type_json> "
            "<output_json>"
        )

        sys.exit(1)

    pipeline = StructurePipeline()

    pipeline.process(
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
    )


if __name__ == "__main__":
    main()