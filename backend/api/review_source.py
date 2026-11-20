"""Render original pages without using the browser's opaque PDF iframe."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import RLock

from PIL import Image, ImageOps
import pypdfium2 as pdfium

_render_lock = RLock()  # PDFium is not thread-safe.


@lru_cache(maxsize=16)
def render_source_page(path: str, modified: int, page_index: int) -> bytes:
    with _render_lock:
        if Path(path).suffix.lower() == '.pdf':
            with pdfium.PdfDocument(path) as document:
                if not 0 <= page_index < len(document):
                    raise IndexError('Original page not found.')
                page = document[page_index]
                try:
                    bitmap = page.render(scale=min(2.0, 1600 / max(page.get_size())))
                    try:
                        image = bitmap.to_pil().copy()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
        else:
            with Image.open(path) as source:
                source.seek(page_index)
                image = ImageOps.exif_transpose(source).convert('RGB')
        try:
            image.thumbnail((1600, 2200))
            output = BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()
        finally:
            image.close()
