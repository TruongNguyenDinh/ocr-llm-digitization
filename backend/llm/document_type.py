import json

from .classifier import DocumentClassifier


class DocumentTypeDetector:
    def __init__(self):
        self.classifier = DocumentClassifier()

    def detect(self, input_path: str) -> dict:
        with open(
            input_path,
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

        blocks = []

        for page in data["pages"]:
            for block in page["blocks"]:
                text = block.get(
                    "corrected_text",
                    block.get("text", ""),
                ).strip()

                if text:
                    blocks.append(text)

        document_text = "\n".join(blocks)

        result = self.classifier.classify(
            document_text
        )

        return result