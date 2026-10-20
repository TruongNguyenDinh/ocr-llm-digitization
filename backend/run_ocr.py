import argparse

from backend.ocr_vl.pipeline import process_document


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run PaddleOCR-VL on one image or PDF."
    )
    parser.add_argument("input_file", help="Path to an image or PDF document")
    parser.add_argument(
        "--output-root",
        default="data/raw",
        help="Directory where the document output folder is created",
    )
    args = parser.parse_args()

    try:
        result = process_document(args.input_file, output_root=args.output_root)
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    print(f"OCR completed: {result['output_dir']}")
    for output_path in result["outputs"]:
        print(output_path)


if __name__ == "__main__":
    main()
