import sys

from backend.ocr.pipeline import OCRPipeline


def main():

    if len(sys.argv) != 3:

        print(
            "Usage:\n"
            "python -m backend.run_ocr "
            "<document_dir> <output_json>"
        )

        sys.exit(1)

    document_dir = sys.argv[1]
    output_json = sys.argv[2]

    pipeline = OCRPipeline()

    pipeline.process_document(
        document_dir,
        output_json,
    )

    print(
        f"\nOCR completed: {output_json}"
    )


if __name__ == "__main__":
    main()