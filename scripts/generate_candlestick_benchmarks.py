"""Generate deterministic Lightweight Charts candlestick-chart benchmark fixtures."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile

from PIL import Image

try:
    from synthetic_candlestick_cases import (
        PALETTES,
        apply_geometry,
        bollinger_bands,
        case_definitions,
        generate_ohlc,
        simple_moving_average,
    )
except ImportError:  # pragma: no cover - package-style invocation
    from .synthetic_candlestick_cases import (
        PALETTES,
        apply_geometry,
        bollinger_bands,
        case_definitions,
        generate_ohlc,
        simple_moving_average,
    )


ROOT = Path(__file__).resolve().parent
RENDERER_ROOT = ROOT.parent
SCHEMA_VERSION = 1


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _render_spec(case: dict) -> tuple[dict, list[dict]]:
    rows = apply_geometry(generate_ohlc(case["seed"], case["count"]), case["geometry"])
    palette = PALETTES[case["palette"]]
    rendered_candles: list[dict] = []
    for row in rows:
        candle = dict(row)
        if case["body_style"] == "hollow_rise" and row["close"] >= row["open"]:
            candle.update(
                {
                    "color": palette["background"],
                    "borderColor": palette["up"],
                    "wickColor": palette["up"],
                }
            )
        rendered_candles.append(candle)

    line_series: list[dict] = []
    for number, overlay in enumerate(case["overlays"], start=1):
        if overlay["kind"] == "ma":
            line_series.append(
                {
                    "id": f"ma{overlay['period']}_{number}",
                    "kind": "ma",
                    "source": {"field": "close", "period": overlay["period"]},
                    "color": overlay["color"],
                    "width": overlay["width"],
                    "data": simple_moving_average(rows, overlay["period"]),
                }
            )
        elif overlay["kind"] == "bollinger":
            bands = bollinger_bands(rows, overlay["period"], overlay["multiplier"])
            for band in ["upper", "middle", "lower"]:
                line_series.append(
                    {
                        "id": f"bollinger_{band}_{number}",
                        "kind": f"bollinger_{band}",
                        "source": {
                            "field": "close",
                            "period": overlay["period"],
                            "multiplier": overlay["multiplier"],
                            "population_standard_deviation": True,
                        },
                        "color": overlay["colors"][band],
                        "width": overlay["width"],
                        "data": bands[band],
                    }
                )
        else:
            raise ValueError(f"unsupported overlay kind: {overlay['kind']}")

    candlestick = {
        "upColor": palette["up"],
        "downColor": palette["down"],
        "borderUpColor": palette["up"],
        "borderDownColor": palette["down"],
        "wickUpColor": palette["up"],
        "wickDownColor": palette["down"],
        "borderVisible": True,
        "priceLineVisible": False,
        "lastValueVisible": False,
    }
    return (
        {
            "schema_version": SCHEMA_VERSION,
            "case_id": case["case_id"],
            "width": case["width"],
            "height": case["height"],
            "theme": {
                "background": palette["background"],
                "text": palette["text"],
                "grid": palette["grid"],
            },
            "candlestick": candlestick,
            "candles": rendered_candles,
            "overlays": line_series,
            "indicator_definitions": case["overlays"],
            "body_style": case["body_style"],
            "geometry": case["geometry"],
            "seed": case["seed"],
        },
        rows,
    )


def _style_configs(case: dict, metadata: dict, render_spec: dict) -> list[dict]:
    centers = metadata["candle_x_centers"]
    spacing = statistics.median(
        centers[index + 1] - centers[index] for index in range(len(centers) - 1)
    )
    min_width = max(2, math.floor(spacing * 0.45))
    max_width = max(min_width + 2, math.ceil(spacing * 0.95))
    palette = PALETTES[case["palette"]]
    occluders = sorted({overlay["color"].upper() for overlay in render_spec["overlays"]})

    def style(style_id: str, kind: str, color: str, direction: str) -> dict:
        geometry = {
            "min_body_width_px": min_width,
            "max_body_width_px": max_width,
            "min_body_height_px": 2,
            "min_vertical_length_px": 2,
            "max_wick_center_offset_px": 2,
            "max_wick_connection_gap_px": 2,
        }
        if occluders:
            geometry.update(
                {
                    "verified_occluder_colors": occluders,
                    "verified_occluder_tolerance": 14,
                    "max_occlusion_gap_px": max(4, math.ceil(spacing * 0.22)),
                    "occluder_role": "topology_only_not_numeric_fill",
                }
            )
            if kind == "filled":
                fragment_alignment = max(3, max_width - min_width)
                geometry.update(
                    {
                        "bridge_filled_body_fragments": True,
                        "max_body_occlusion_gap_px": max(4, math.ceil(spacing * 0.22)),
                        "max_body_fragment_center_delta_px": fragment_alignment,
                        "max_body_fragment_edge_delta_px": fragment_alignment,
                        "max_body_fragment_width_delta_px": fragment_alignment,
                        "max_body_fragment_union_width_px": max_width,
                        "min_body_fragment_horizontal_overlap_px": max(
                            3, math.floor(min_width * 0.25)
                        ),
                        "body_occluder_vertical_radius_px": 1,
                        "min_body_occluder_row_coverage": 1.0,
                        "min_occluder_color_separation": 1.0,
                    }
                )
        return {
            "id": style_id,
            "kind": kind,
            "colors": [color.upper()],
            "tolerance": 16,
            "direction": direction,
            "geometry": geometry,
        }

    rise_kind = "outline" if case["body_style"] == "hollow_rise" else "filled"
    return [
        style("rise", rise_kind, palette["up"], "close_above_open"),
        style("fall", "filled", palette["down"], "open_above_close"),
    ]


def _write_truth(path: Path, rows: list[dict], centers: list[float]) -> None:
    if len(rows) != len(centers):
        raise ValueError("truth rows and renderer x centers differ")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["date", "open", "high", "low", "close", "x_center_px"],
        )
        writer.writeheader()
        for row, center in zip(rows, centers, strict=True):
            writer.writerow(
                {
                    "date": row["time"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "x_center_px": f"{center:.6f}",
                }
            )


def _manifest(case: dict, case_dir: Path, rows: list[dict], render_spec: dict, metadata: dict) -> dict:
    image_path = case_dir / "original.png"
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest().upper()
    anchors = metadata["price_anchors"]
    price_per_pixel = abs(anchors[0]["value"] - anchors[1]["value"]) / abs(
        anchors[0]["pixel"] - anchors[1]["pixel"]
    )
    centers = metadata["candle_x_centers"]
    spacing = statistics.median(
        centers[index + 1] - centers[index] for index in range(len(centers) - 1)
    )
    overlay_colors = sorted({item["color"].upper() for item in render_spec["overlays"]})
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": case["case_id"],
        "kind": "synthetic",
        "family": case["family"],
        "classification": case["classification"],
        "stressors": {
            "theme": case["palette"],
            "body_style": case["body_style"],
            "geometry": case["geometry"],
            "near_color_overlay": case["near_color_overlay"],
            "overlay_ids": [item["id"] for item in render_spec["overlays"]],
        },
        "tuning_case": True,
        "held_out": False,
        "image": {
            "file": "original.png",
            "sha256": digest,
            "width": metadata["width"],
            "height": metadata["height"],
            "coordinate_space": "original_raster_pixels",
        },
        "truth": {
            "file": "truth.csv",
            "source": "deterministic_local_generator",
            "seed": case["seed"],
            "mapping": "date identifies rows; OHLC is source truth; x_center_px comes from renderer timeToCoordinate",
            "detector_access": False,
        },
        "renderer": metadata["renderer"],
        "calibration_provenance": {
            "method": "lightweight_charts_coordinate_api",
            "price_api": "candlestickSeries.coordinateToPrice",
            "time_api": "chart.timeScale().timeToCoordinate",
        },
        "overlay_policy": {
            "colors": overlay_colors,
            "occluder_role": "topology_only_not_numeric_fill" if overlay_colors else "not_applicable",
            "values_used_for_ohlc": False,
        },
        "extraction_config": {
            "plot_bounds": metadata["plot_bounds"],
            "price_axis": {
                "scale": "linear",
                "anchors": anchors,
                "provenance": "deterministic_renderer_geometry",
            },
            "styles": _style_configs(case, metadata, render_spec),
            "duplicate_distance_px": max(2, round(spacing * 0.35, 3)),
        },
        "evaluation": {
            "x_match_tolerance_px": max(3, round(spacing * 0.15, 3)),
            "required": {
                "clean_case_precision": 1.0,
                "clean_case_recall": 1.0,
                "clean_case_f1": 1.0,
                "max_field_mae": round(price_per_pixel * 2.5, 8),
                "max_field_absolute_error": round(price_per_pixel * 5.0, 8),
                "max_unsafe_false_accepts": 0,
                "stress_case_failures_are_reported_not_omitted": True,
            },
        },
        "limitations": [
            "single renderer and template family",
            "synthetic tuning evidence only",
            "dates are evaluator identifiers, not OCR targets",
            "overlay values cannot supply OHLC",
        ],
    }


def _case_readme(case: dict, render_spec: dict) -> str:
    overlay_names = ", ".join(item["id"] for item in render_spec["overlays"]) or "none"
    return (
        f"# {case['case_id']}\n\n"
        f"Deterministic Lightweight Charts synthetic {case['classification']} case.\n\n"
        f"- Family: `{case['family']}`\n"
        f"- Theme: `{case['palette']}`\n"
        f"- Body style: `{case['body_style']}`\n"
        f"- Geometry: `{case['geometry']}`\n"
        f"- Overlays: {overlay_names}\n"
        f"- Seed: `{case['seed']}`\n"
        "- Status: tuning/regression only; not held out.\n"
        "- Overlay pixels are topology-only occluders and never numeric OHLC fill.\n"
    )


def generate_suite(output_dir: Path | str) -> Path:
    destination = Path(output_dir).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty benchmark directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    cases_index: list[dict] = []
    try:
        for case in case_definitions():
            case_dir = staging / case["case_id"]
            case_dir.mkdir()
            render_spec, rows = _render_spec(case)
            _write_json(case_dir / "render-spec.json", render_spec)
            completed = subprocess.run(
                [
                    "node",
                    str(RENDERER_ROOT / "render_lwc_case.mjs"),
                    "--spec",
                    str(case_dir / "render-spec.json"),
                    "--output-dir",
                    str(case_dir),
                ],
                cwd=RENDERER_ROOT,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"renderer failed for {case['case_id']}: {completed.stderr or completed.stdout}"
                )
            metadata = json.loads((case_dir / "render-metadata.json").read_text(encoding="utf-8"))
            _write_truth(case_dir / "truth.csv", rows, metadata["candle_x_centers"])
            manifest = _manifest(case, case_dir, rows, render_spec, metadata)
            _write_json(case_dir / "manifest.json", manifest)
            (case_dir / "README.md").write_text(_case_readme(case, render_spec), encoding="utf-8")
            cases_index.append(
                {
                    "case_id": case["case_id"],
                    "path": case["case_id"],
                    "family": case["family"],
                    "classification": case["classification"],
                    "image_sha256": manifest["image"]["sha256"],
                }
            )
        suite = {
            "schema_version": SCHEMA_VERSION,
            "suite_id": "synthetic_lwc_v1",
            "renderer_family": "lightweight-charts@5.2.0",
            "kind": "synthetic_tuning_regression",
            "held_out": False,
            "cases": cases_index,
        }
        _write_json(staging / "suite.json", suite)
        (staging / "README.md").write_text(
            "# Lightweight Charts synthetic candlestick-chart benchmark\n\n"
            "Sixteen deterministic tuning/regression cases rendered with Lightweight Charts 5.2.0. "
            "This single-renderer suite is not held out and does not establish real-raster generalization.\n",
            encoding="utf-8",
        )
        validate_suite(staging)
        if destination.exists():
            destination.rmdir()
        staging.replace(destination)
        return destination
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def validate_suite(suite_dir: Path | str) -> None:
    root = Path(suite_dir)
    suite = json.loads((root / "suite.json").read_text(encoding="utf-8"))
    if len(suite.get("cases", [])) != 16:
        raise ValueError("suite must contain exactly 16 cases")
    ids = [item["case_id"] for item in suite["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("case ids must be unique")
    hashes: set[str] = set()
    for item in suite["cases"]:
        case_dir = root / item["path"]
        required = ["original.png", "truth.csv", "manifest.json", "render-spec.json", "render-metadata.json", "README.md"]
        missing = [name for name in required if not (case_dir / name).exists()]
        if missing:
            raise ValueError(f"{item['case_id']} missing: {missing}")
        manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
        image_bytes = (case_dir / "original.png").read_bytes()
        digest = hashlib.sha256(image_bytes).hexdigest().upper()
        if digest != manifest["image"]["sha256"]:
            raise ValueError(f"source hash mismatch: {item['case_id']}")
        hashes.add(digest)
        with Image.open(case_dir / "original.png") as image:
            if image.size != (manifest["image"]["width"], manifest["image"]["height"]):
                raise ValueError(f"source dimensions mismatch: {item['case_id']}")
            extrema = image.convert("RGB").getextrema()
            if all(low == high for low, high in extrema):
                raise ValueError(f"blank raster: {item['case_id']}")
        isolated = json.dumps(manifest["extraction_config"], sort_keys=True)
        if any(token in isolated for token in ["truth", "expected_count", "x_center_px", "2026-"]):
            raise ValueError(f"truth leaked into extraction config: {item['case_id']}")
        with (case_dir / "truth.csv").open(newline="", encoding="utf-8") as handle:
            truth = list(csv.DictReader(handle))
        metadata = json.loads((case_dir / "render-metadata.json").read_text(encoding="utf-8"))
        if len(truth) != len(metadata["candle_x_centers"]):
            raise ValueError(f"truth/coordinate count mismatch: {item['case_id']}")
    if len(hashes) != 16:
        raise ValueError("each case must have a distinct raster hash")


def compare_suite_reproducibility(first_dir: Path | str, second_dir: Path | str) -> dict:
    """Compare two generated trees byte-for-byte by relative path."""
    first = Path(first_dir)
    second = Path(second_dir)
    first_files = {path.relative_to(first).as_posix(): path for path in first.rglob("*") if path.is_file()}
    second_files = {path.relative_to(second).as_posix(): path for path in second.rglob("*") if path.is_file()}
    mismatches: list[dict] = []
    for relative in sorted(set(first_files) | set(second_files)):
        if relative not in first_files:
            mismatches.append({"file": relative, "reason": "missing_from_first"})
        elif relative not in second_files:
            mismatches.append({"file": relative, "reason": "missing_from_second"})
        elif first_files[relative].read_bytes() != second_files[relative].read_bytes():
            mismatches.append({"file": relative, "reason": "byte_mismatch"})
    return {
        "reproducible": not mismatches,
        "compared_file_count": len(set(first_files) | set(second_files)),
        "mismatches": mismatches,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output = generate_suite(args.output_dir)
    print(f"SUITE_OUTPUT={output}")


if __name__ == "__main__":
    main()
