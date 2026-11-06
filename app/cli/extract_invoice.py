"""Command line: extract invoice images into JSON with the configured model.

Only PNG and JPEG are accepted. Convert a PDF page first, for example on macOS:
    sips -s format png --resampleHeight 1754 invoice_scan.pdf --out invoice_scan.png
"""

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import get_settings
from app.logging_config import setup_logging
from app.services.invoice_extractor import (
    MAX_IMAGE_BYTES,
    InvoiceExtractionError,
    InvoiceExtractor,
    image_type,
)
from app.services.llm_client import LlmClient, LlmConfigError, LlmError

logger = logging.getLogger(__name__)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract invoice images into JSON.")
    parser.add_argument("images", type=Path, nargs="+")
    parser.add_argument("--prompt-version", default="v1")
    return parser.parse_args(argv)


def _read_images(paths: Sequence[Path]) -> list[tuple[Path, bytes]]:
    images: list[tuple[Path, bytes]] = []
    for path in paths:
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise InvoiceExtractionError(f"{path.name}: larger than {MAX_IMAGE_BYTES} bytes")
        data = path.read_bytes()
        try:
            image_type(data)
        except InvoiceExtractionError as exc:
            raise InvoiceExtractionError(f"{path.name}: {exc}") from exc
        images.append((path, data))
    return images


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    setup_logging()
    try:
        images = _read_images(args.images)
    except (OSError, InvoiceExtractionError) as exc:
        logger.error("%s", exc)
        return 1
    try:
        llm = LlmClient.from_settings(get_settings())
    except LlmConfigError as exc:
        logger.error("%s", exc)
        return 1

    failed = False
    with llm:
        extractor = InvoiceExtractor(llm, args.prompt_version)
        for path, data in images:
            try:
                result = extractor.extract(data)
            except (InvoiceExtractionError, LlmError) as exc:
                logger.error("%s: %s", path.name, exc)
                failed = True
                continue
            output = {
                "file": path.name,
                "model": result.model,
                "prompt": result.prompt_version,
                "repaired": result.repaired,
                "seconds": round(result.latency_seconds, 1),
                "invoice": result.invoice.model_dump(mode="json"),
            }
            sys.stdout.write(json.dumps(output, indent=2) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
