import sys

from backend.preprocessing.pipeline import process_document


def main():

    if len(sys.argv) != 3:
        print(
            "Usage: "
            "python -m backend.preprocess "
            "<input_file> <output_dir>"
        )
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2]

    pages = process_document(
        input_file,
        output_dir,
    )

    print("\nProcessing completed.")

    for page in pages:
        print(f"✓ {page}")


if __name__ == "__main__":
    main()