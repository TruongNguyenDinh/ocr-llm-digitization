import json

from .client import QwenClient


DOCUMENT_CLASSIFICATION_PROMPT = """Bạn là hệ thống phân loại tài liệu.

Hãy xác định loại tài liệu dựa trên nội dung được cung cấp.

Các loại tài liệu được phép:
- research_paper
- report
- letter
- official_document
- invoice
- form
- resume
- article
- book
- receipt
- other

Quy tắc:
- Chỉ chọn một loại.
- Không tự ý tạo loại mới.
- Dựa vào cấu trúc và nội dung tổng thể.
- Không được sửa nội dung OCR.
- Trả về JSON hợp lệ.
- Không trả về markdown.
- Không giải thích bên ngoài JSON.

Định dạng bắt buộc:

{{
  "document_type": "research_paper",
  "confidence": 0.95
}}

Nội dung tài liệu:

{text}

Chỉ trả về JSON:
"""


class DocumentClassifier:
    def __init__(self):
        self.client = QwenClient()

    def classify(self, text: str) -> dict:
        prompt = DOCUMENT_CLASSIFICATION_PROMPT.format(
            text=text
        )

        response = self.client.generate(prompt).strip()

        try:
            return json.loads(response)

        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}")

            if start != -1 and end != -1:
                try:
                    return json.loads(
                        response[start:end + 1]
                    )
                except json.JSONDecodeError:
                    pass

            raise ValueError(
                f"Qwen returned invalid JSON:\n{response}"
            )