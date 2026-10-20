import argparse
from pathlib import Path

from backend.document_workflow import prepare_document


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run PaddleOCR-VL and prepare local LLM suggestions for review."
    )
    parser.add_argument("input_file", help="Path to an image or PDF document")
    parser.add_argument(
        "--output-root",
        default="data/raw",
        help="Directory where raw OCR and review outputs are written",
    )
    args = parser.parse_args()

    def report_progress(event: dict[str, object]) -> None:
        print(
            f"OCR completed {event['completed']}/{event['total']} "
            f"(page {event['page_number']})",
            flush=True,
        )

    try:
        draft = prepare_document(
            args.input_file,
            progress_callback=report_progress,
            output_root=args.output_root,
        )
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    review_path = Path(draft.raw_document_dir) / "review.json"
    print(f"Review ready: {review_path}")
    print(f"Label: {draft.metadata.label_code} ({draft.metadata.label_name})")
    print("Final storage requires explicit user-approved text for every page.")


if __name__ == "__main__":
    main()
