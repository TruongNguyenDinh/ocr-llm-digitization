from .client import QwenClient
from .prompts import OCR_CORRECTION_PROMPT


class OCRCorrector:
    def __init__(self):
        self.client = QwenClient()

    def correct(self, text: str) -> str:
        prompt = OCR_CORRECTION_PROMPT.format(
            text=text
        )

        result = self.client.generate(prompt)

        return result.strip()