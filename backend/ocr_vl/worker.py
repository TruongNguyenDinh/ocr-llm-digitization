from __future__ import annotations

import argparse
import contextlib
import json
import sys
import traceback
from pathlib import Path
from typing import Any

from .pipeline import process_document


def _emit_event(stream: Any, event: dict[str, Any]) -> None:
    stream.write("OCR_EVENT:" + json.dumps(event, ensure_ascii=False) + "\n")
    stream.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one isolated PaddleOCR-VL job.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    protocol_stream = sys.stdout

    def on_progress(event: dict[str, Any]) -> None:
        _emit_event(protocol_stream, event)

    try:
        # Paddle/PaddleX may print diagnostics to stdout. Keep protocol frames clean.
        with contextlib.redirect_stdout(sys.stderr):
            process_document(
                args.source,
                output_root=args.output_root,
                progress_callback=on_progress,
            )
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        _emit_event(protocol_stream, {"event": "failed", "error": str(exc)})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
