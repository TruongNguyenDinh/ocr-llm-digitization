import json

from .client import QwenClient


STRUCTURE_PROMPT = """Bạn là hệ thống phân tích cấu trúc tài liệu.

Loại tài liệu:
{document_type}

Hãy phân loại từng block văn bản thành một loại cấu trúc phù hợp.

Các loại block được phép:

- title
- subtitle
- author
- date
- heading
- subheading
- paragraph
- abstract
- caption
- figure
- table
- list
- header
- footer
- reference
- address
- subject
- salutation
- closing
- signature
- unknown

Quy tắc:
- Không sửa nội dung.
- Không thay đổi thứ tự block.
- Không tạo block mới.
- Không xóa block.
- Chỉ xác định loại của từng block.
- Trả về JSON hợp lệ.
- Không trả về markdown.

Danh sách block:

{blocks}

Trả về JSON theo đúng cấu trúc:

{{
  "blocks": [
    {{
      "index": 0,
      "type": "title"
    }}
  ]
}}
"""


class StructureAnalyzer:
    def __init__(self):
        self.client = QwenClient()

    def analyze(
        self,
        document_type: str,
        blocks: list,
    ) -> dict:

        block_text = []

        for index, block in enumerate(blocks):
            block_text.append(
                f"[{index}] {block['text']}"
            )

        prompt = STRUCTURE_PROMPT.format(
            document_type=document_type,
            blocks="\n".join(block_text),
        )

        response = self.client.generate(prompt).strip()

        try:
            return json.loads(response)

        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}")

            if start != -1 and end != -1:
                return json.loads(
                    response[start:end + 1]
                )

            raise ValueError(
                f"Invalid JSON from Qwen:\n{response}"
            )