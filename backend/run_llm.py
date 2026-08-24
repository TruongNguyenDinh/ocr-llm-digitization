import sys

from backend.llm.pipeline import LLMPipeline


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python -m backend.run_llm "
            "<input_json> <output_json>"
        )
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    pipeline = LLMPipeline()

    pipeline.process(
        input_path,
        output_path,
    )

    print(f"LLM completed: {output_path}")


if __name__ == "__main__":
    main()