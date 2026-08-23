from pathlib import Path

import pymupdf


def pdf_to_images(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = 300,
) -> list[Path]:

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    document = pymupdf.open(pdf_path)

    scale = dpi / 72

    matrix = pymupdf.Matrix(
        scale,
        scale,
    )

    output_paths = []

    for page_index, page in enumerate(document):

        pixmap = page.get_pixmap(
            matrix=matrix,
            alpha=False,
        )

        output_path = (
            output_dir
            / f"page_{page_index + 1:03d}.png"
        )

        pixmap.save(str(output_path))

        output_paths.append(output_path)

    document.close()

    return output_paths