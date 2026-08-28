"""Candidate candlestick digitizer with source-locked evidence outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kline_extractor import extract_klines, write_extraction_artifacts


def load_extraction_config(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if "extraction_config" not in document:
        return document
    config = json.loads(json.dumps(document["extraction_config"]))
    image = document["image"]
    config["source_contract"] = {
        "sha256": image["sha256"],
        "width": image["width"],
        "height": image["height"],
    }
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Source-locked extraction config or benchmark manifest JSON.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = load_extraction_config(args.config)
    result, metadata = extract_klines(args.input, config)
    output = write_extraction_artifacts(args.input, result, metadata, args.output_dir)
    print(f"EVIDENCE_OUTPUT={output}")
    print(f"NUMERIC_OUTPUT_AUTHORIZED={str(result.numeric_output_authorized).lower()}")
    if not result.numeric_output_authorized:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
