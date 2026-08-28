"""Run an isolated candlestick extraction and evaluate it against benchmark truth."""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from evaluate_kline import evaluate_ohlc
from kline_extractor import extract_klines, write_extraction_artifacts
import legacy_digitize_kline as legacy


def load_manifest(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def extractor_config_from_manifest(manifest: dict) -> dict:
    config = json.loads(json.dumps(manifest["extraction_config"]))
    image = manifest["image"]
    config["source_contract"] = {
        "sha256": image["sha256"],
        "width": image["width"],
        "height": image["height"],
    }
    return config


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_comparison_csv(path: Path, rows: list[dict]) -> None:
    if rows:
        fieldnames = list(rows[0])
    else:
        fieldnames = ["detected_index", "truth_index", "x_error_px"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _legacy_rows(image_path: Path, manifest: dict) -> list[dict]:
    config = manifest["extraction_config"]
    styles = {style["kind"]: style for style in config["styles"]}
    filled = styles["filled"]
    outline = styles["outline"]
    pixels = np.asarray(Image.open(image_path).convert("RGB"))
    filled_colors = [legacy.parse_color(value) for value in filled["colors"]]
    outline_colors = [legacy.parse_color(value) for value in outline["colors"]]
    tolerance = max(float(filled["tolerance"]), float(outline["tolerance"]))
    with contextlib.redirect_stdout(io.StringIO()):
        candidates = legacy.detect_klines(
            pixels,
            tuple(config["plot_bounds"]),
            filled_colors,
            outline_colors,
            tolerance,
        )
        anchors = config["price_axis"]["anchors"]
        rows = legacy.calibrate(
            candidates,
            anchors[1]["pixel"],
            anchors[1]["value"],
            anchors[0]["pixel"],
            anchors[0]["value"],
        )
    return rows


def run_benchmark(case_dir: Path | str, output_dir: Path | str) -> Path:
    case = Path(case_dir)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty evidence directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    extraction_dir = output / "extraction"
    validation_dir = output / "validation"
    validation_dir.mkdir(parents=True, exist_ok=False)

    manifest = load_manifest(case / "manifest.json")
    image_path = case / manifest["image"]["file"]
    config = extractor_config_from_manifest(manifest)
    result, metadata = extract_klines(image_path, config)
    metadata["case_id"] = manifest["case_id"]
    write_extraction_artifacts(image_path, result, metadata, extraction_dir)

    detected = _read_csv(extraction_dir / "data.csv")
    truth = _read_csv(case / manifest["truth"]["file"])
    anchors = manifest["extraction_config"]["price_axis"]["anchors"]
    price_range = abs(float(anchors[0]["value"]) - float(anchors[1]["value"]))
    evaluation = evaluate_ohlc(
        detected,
        truth,
        tolerance_px=float(manifest["evaluation"]["x_match_tolerance_px"]),
        price_range=price_range,
    )
    evaluation.update(
        {
            "schema_version": 1,
            "case_id": manifest["case_id"],
            "kind": manifest["kind"],
            "tuning_case": manifest["tuning_case"],
            "held_out": manifest["held_out"],
            "required_gates": manifest["evaluation"]["required"],
        }
    )
    _write_comparison_csv(validation_dir / "comparison.csv", evaluation["comparisons"])
    (validation_dir / "evaluation.json").write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    baseline_dir = output / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=False)
    style_kinds = {style["kind"] for style in manifest["extraction_config"]["styles"]}
    legacy_applicable = {"filled", "outline"}.issubset(style_kinds)
    baseline_rows = _legacy_rows(image_path, manifest) if legacy_applicable else []
    baseline_evaluation = evaluate_ohlc(
        baseline_rows,
        truth,
        tolerance_px=float(manifest["evaluation"]["x_match_tolerance_px"]),
        price_range=price_range,
    )
    baseline_evaluation.update(
        {
            "schema_version": 1,
            "case_id": manifest["case_id"],
            "implementation": "legacy_digitize_kline.py",
            "status": "completed" if legacy_applicable else "not_applicable",
            "reason": None if legacy_applicable else "legacy_requires_filled_and_outline_styles",
        }
    )
    _write_comparison_csv(
        baseline_dir / "comparison.csv", baseline_evaluation["comparisons"]
    )
    (baseline_dir / "evaluation.json").write_text(
        json.dumps(baseline_evaluation, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output = run_benchmark(args.case_dir, args.output_dir)
    print(f"BENCHMARK_OUTPUT={output}")


if __name__ == "__main__":
    main()
