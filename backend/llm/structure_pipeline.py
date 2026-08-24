import json
from pathlib import Path

from .structure import StructureAnalyzer


class StructurePipeline:
    def __init__(self):
        self.analyzer = StructureAnalyzer()

    def process(
        self,
        input_path: str,
        document_type_path: str,
        output_path: str,
    ):

        with open(
            input_path,
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

        with open(
            document_type_path,
            "r",
            encoding="utf-8",
        ) as f:
            document_type = json.load(f)

        doc_type = document_type[
            "document_type"
        ]

        for page in data["pages"]:

            blocks = page["blocks"]

            analysis = self.analyzer.analyze(
                doc_type,
                blocks,
            )

            for item in analysis["blocks"]:

                index = item["index"]

                if index < 0 or index >= len(blocks):
                    continue

                blocks[index]["type"] = item["type"]

        data["document_type"] = doc_type

        output = Path(output_path)

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(
            output,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
            )

        print(
            f"Document type: {doc_type}"
        )

        print(
            f"Output: {output_path}"
        )