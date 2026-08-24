import json
from pathlib import Path

from .correction import OCRCorrector


class LLMPipeline:
    def __init__(self, confidence_threshold: float = 0.95):
        self.corrector = OCRCorrector()
        self.confidence_threshold = confidence_threshold

    def process(
        self,
        input_path: str,
        output_path: str,
    ):
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        total_blocks = 0
        processed_blocks = 0
        changed_blocks = 0

        for page in data["pages"]:
            for block in page["blocks"]:
                total_blocks += 1

                text = block.get("text", "").strip()

                if not text:
                    block["corrected_text"] = ""
                    continue

                confidence = block.get("confidence", 1.0)

                if confidence >= self.confidence_threshold:
                    block["corrected_text"] = text
                    continue

                processed_blocks += 1

                corrected_text = self.corrector.correct(text)

                block["corrected_text"] = corrected_text

                if corrected_text != text:
                    changed_blocks += 1

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
            )

        print(f"Total blocks: {total_blocks}")
        print(f"LLM processed: {processed_blocks}")
        print(f"Changed: {changed_blocks}")
        print(f"Output: {output_path}")