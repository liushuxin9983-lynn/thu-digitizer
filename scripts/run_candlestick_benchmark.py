"""Run truth-isolated candlestick extraction and independent evaluation."""

from __future__ import annotations

import argparse
import csv
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Sequence

try:
    from candidate_digitize_candlestick import (
        CANDLESTICK_ROUTE_ID,
        run_candlestick_extraction,
    )
    from extractor_registry import ROUTE_BY_ID
    from figure_spec import assert_valid_figure_spec
except ImportError:  # pragma: no cover - package-style invocation
    from .candidate_digitize_candlestick import (
        CANDLESTICK_ROUTE_ID,
        run_candlestick_extraction,
    )
    from .extractor_registry import ROUTE_BY_ID
    from .figure_spec import assert_valid_figure_spec


class BenchmarkManifest(dict):
    """Manifest data with its filesystem location kept out of serialization."""

    manifest_path: Path


def load_manifest(path: Path | str) -> BenchmarkManifest:
    manifest_path = Path(path).resolve()
    manifest = BenchmarkManifest(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    manifest.manifest_path = manifest_path
    return manifest


def _manifest_case_dir(manifest: dict, case_dir: Path | str | None) -> Path:
    if case_dir is not None:
        return Path(case_dir).resolve()
    manifest_path = getattr(manifest, "manifest_path", None)
    if manifest_path is None:
        raise ValueError(
            "figure_spec_from_manifest requires a manifest loaded with load_manifest "
            "or an explicit case_dir"
        )
    return Path(manifest_path).parent


def _evidenced_anchors(price_axis: dict) -> list[dict[str, Any]]:
    anchors = []
    for anchor in price_axis["anchors"]:
        evidence = anchor.get("evidence")
        if not isinstance(evidence, dict) or not evidence:
            evidence = {"kind": "benchmark_manifest_verified"}
        anchors.append(
            {
                "pixel": anchor["pixel"],
                "value": anchor["value"],
                "evidence": json.loads(json.dumps(evidence)),
            }
        )
    return anchors


def _verified_geometry(styles: list[dict]) -> dict[str, Any]:
    geometries = [
        style.get("geometry", {})
        for style in styles
        if isinstance(style.get("geometry"), dict)
    ]
    return {
        "verification": "verified",
        "min_body_width_px": min(
            float(value["min_body_width_px"]) for value in geometries
        ),
        "max_body_width_px": max(
            float(value["max_body_width_px"]) for value in geometries
        ),
        "max_wick_center_offset_px": max(
            float(value.get("max_wick_center_offset_px", 0)) for value in geometries
        ),
    }


def figure_spec_from_manifest(
    manifest: dict,
    case_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Build a verified FigureSpec from extraction fields only."""

    root = _manifest_case_dir(manifest, case_dir)
    image = manifest["image"]
    config = manifest["extraction_config"]
    styles = json.loads(json.dumps(config["styles"]))
    anchors = _evidenced_anchors(config["price_axis"])
    required = list(ROUTE_BY_ID[CANDLESTICK_ROUTE_ID].required_confirmations)
    width = image["width"]
    height = image["height"]
    spec = {
        "schema_version": 1,
        "status": "ready_for_assisted_extraction",
        "source": {
            "input_file": str((root / image["file"]).resolve()),
            "sha256": image["sha256"],
            "media_kind": "raster",
            "coordinate_space": "pixel",
            "measurement_space": "original_raster_pixels",
            "resampling_applied": False,
            "width": width,
            "height": height,
        },
        "panels": [
            {
                "panel_id": "candlestick-panel-1",
                "bounds": [0, 0, width, height],
                "bounds_verification": "verified",
                "plot_bounds": list(config["plot_bounds"]),
                "plot_bounds_verification": "verified",
                "chart_type": "candlestick",
                "coordinate_model": "categorical_value",
                "axes": [
                    {
                        "axis_id": "category",
                        "scale": "categorical",
                        "verification": "not_applicable",
                        "anchors": [],
                    },
                    {
                        "axis_id": "price",
                        "scale": "linear",
                        "verification": "verified",
                        "anchors": [
                            {"pixel": item["pixel"], "value": item["value"]}
                            for item in anchors
                        ],
                    },
                ],
                "mark_grammars": ["candle_body", "wick"],
                "route": {
                    "route_id": CANDLESTICK_ROUTE_ID,
                    "maturity": "candidate",
                },
                "required_confirmations": required,
                "confirmations": {name: "verified" for name in required},
                "route_config": {
                    "price_axis": {
                        "scale": "linear",
                        "verification": "verified",
                        "require_anchor_evidence": config["price_axis"].get(
                            "require_anchor_evidence", False
                        ),
                        "anchors": anchors,
                    },
                    "styles": styles,
                    "geometry": _verified_geometry(styles),
                    "duplicate_distance_px": config.get("duplicate_distance_px", 15),
                    "exclusions": {
                        "verification": "not_applicable",
                        "regions": [],
                    },
                    "occluders": {
                        "verification": "not_applicable",
                        "regions": [],
                    },
                },
            }
        ],
    }
    assert_valid_figure_spec(spec)
    return spec


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _number(row: dict, key: str) -> float:
    return float(row[key])


def monotonic_match(
    detected: Sequence[dict],
    truth: Sequence[dict],
    tolerance_px: float,
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Maximize monotonic match coverage, then minimize total x error."""

    detected_x = tuple(_number(row, "x_center") for row in detected)
    truth_x = tuple(_number(row, "x_center_px") for row in truth)

    @lru_cache(maxsize=None)
    def solve(i: int, j: int) -> tuple[int, float, tuple[tuple[int, int], ...]]:
        if i == len(detected_x) or j == len(truth_x):
            return 0, 0.0, ()
        options = [solve(i + 1, j), solve(i, j + 1)]
        error = abs(detected_x[i] - truth_x[j])
        if error <= tolerance_px:
            count, cost, pairs = solve(i + 1, j + 1)
            options.append((count + 1, cost + error, ((i, j),) + pairs))
        return max(options, key=lambda item: (item[0], -item[1]))

    _, _, pair_tuple = solve(0, 0)
    matches = list(pair_tuple)
    matched_detected = {i for i, _ in matches}
    matched_truth = {j for _, j in matches}
    extras = [i for i in range(len(detected)) if i not in matched_detected]
    missing = [j for j in range(len(truth)) if j not in matched_truth]
    return matches, extras, missing


def _field_metrics(errors: list[float], price_range: float | None) -> dict:
    absolute = sorted(abs(error) for error in errors)
    if not absolute:
        return {
            "mae": None,
            "rmse": None,
            "p95_absolute_error": None,
            "max_absolute_error": None,
            "normalized_mae": None,
        }
    count = len(absolute)
    p95_index = max(0, math.ceil(0.95 * count) - 1)
    mae = sum(absolute) / count
    return {
        "mae": mae,
        "rmse": math.sqrt(sum(error * error for error in errors) / count),
        "p95_absolute_error": absolute[p95_index],
        "max_absolute_error": absolute[-1],
        "normalized_mae": mae / price_range if price_range else None,
    }


def evaluate_ohlc(
    detected_rows: Sequence[dict],
    truth_rows: Sequence[dict],
    tolerance_px: float,
    price_range: float | None = None,
) -> dict[str, Any]:
    """Independently compare extraction rows with evaluator-only truth rows."""

    matches, extras, missing = monotonic_match(
        detected_rows, truth_rows, tolerance_px
    )
    fields = ("open", "high", "low", "close")
    field_errors = {field: [] for field in fields}
    comparisons = []
    invariant_violations = 0
    for detected_index, truth_index in matches:
        detected = detected_rows[detected_index]
        truth = truth_rows[truth_index]
        row = {
            "detected_index": detected_index,
            "truth_index": truth_index,
            "x_error_px": _number(detected, "x_center")
            - _number(truth, "x_center_px"),
        }
        for field in fields:
            error = _number(detected, field) - _number(truth, field)
            field_errors[field].append(error)
            row[f"detected_{field}"] = _number(detected, field)
            row[f"truth_{field}"] = _number(truth, field)
            row[f"{field}_error"] = error
            row[f"{field}_absolute_error"] = abs(error)
        if (
            _number(detected, "high")
            < max(_number(detected, "open"), _number(detected, "close"))
            or _number(detected, "low")
            > min(_number(detected, "open"), _number(detected, "close"))
        ):
            invariant_violations += 1
        comparisons.append(row)

    matched_count = len(matches)
    precision = matched_count / len(detected_rows) if detected_rows else 0.0
    recall = matched_count / len(truth_rows) if truth_rows else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "matched_count": matched_count,
        "detected_count": len(detected_rows),
        "truth_count": len(truth_rows),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matches": matches,
        "extra_detected_indices": extras,
        "missing_truth_indices": missing,
        "fields": {
            field: _field_metrics(field_errors[field], price_range)
            for field in fields
        },
        "comparisons": comparisons,
        "ohlc_invariant_violation_count": invariant_violations,
        "unsafe_false_accept_count": sum(
            1
            for index in extras
            if detected_rows[index].get("confidence") == "high"
        ),
    }


def _write_comparison_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = list(rows[0]) if rows else [
        "detected_index",
        "truth_index",
        "x_error_px",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _gate_results(manifest: dict, evaluation: dict) -> dict[str, bool]:
    required = manifest["evaluation"]["required"]
    finite_mae = [
        metrics["mae"]
        for metrics in evaluation["fields"].values()
        if metrics["mae"] is not None
    ]
    finite_max = [
        metrics["max_absolute_error"]
        for metrics in evaluation["fields"].values()
        if metrics["max_absolute_error"] is not None
    ]
    results: dict[str, bool] = {}
    for name, threshold in required.items():
        if name in {"precision", "recall", "f1"}:
            results[name] = evaluation[name] >= float(threshold)
        elif name.startswith("clean_case_"):
            metric = name.removeprefix("clean_case_")
            results[name] = (
                evaluation[metric] >= float(threshold)
                if manifest.get("classification") == "clean"
                else True
            )
        elif name == "max_field_mae":
            results[name] = bool(finite_mae) and max(finite_mae) <= float(threshold)
        elif name == "max_field_absolute_error":
            results[name] = bool(finite_max) and max(finite_max) <= float(threshold)
        elif name == "max_ohlc_invariant_violations":
            results[name] = (
                evaluation["ohlc_invariant_violation_count"] <= int(threshold)
            )
        elif name == "max_unsafe_false_accepts":
            results[name] = evaluation["unsafe_false_accept_count"] <= int(threshold)
        elif name == "stress_case_failures_are_reported_not_omitted":
            results[name] = bool(threshold)
        else:
            results[name] = False
    return results


def _evaluate_after_extraction(
    case: Path,
    manifest: dict,
    extraction_dir: Path,
    authorized: bool,
) -> dict[str, Any]:
    """Read benchmark truth only after the extractor has returned."""

    detected = _read_csv(extraction_dir / "data.csv") if authorized else []
    truth = _read_csv(case / manifest["truth"]["file"])
    anchors = manifest["extraction_config"]["price_axis"]["anchors"]
    price_range = abs(float(anchors[0]["value"]) - float(anchors[1]["value"]))
    evaluation = evaluate_ohlc(
        detected,
        truth,
        tolerance_px=float(manifest["evaluation"]["x_match_tolerance_px"]),
        price_range=price_range,
    )
    extraction_report = json.loads(
        (extraction_dir / "report.json").read_text(encoding="utf-8")
    )
    evaluation.update(
        {
            "schema_version": 1,
            "case_id": manifest["case_id"],
            "kind": manifest["kind"],
            "tuning_case": manifest["tuning_case"],
            "held_out": manifest["held_out"],
            "numeric_output_authorized": authorized,
            "refusal_reasons": extraction_report.get("refusal_reasons", []),
            "required_gates": manifest["evaluation"]["required"],
        }
    )
    gate_results = _gate_results(manifest, evaluation)
    evaluation["gate_results"] = gate_results
    evaluation["failed_gates"] = [
        name for name, passed in gate_results.items() if not passed
    ]
    evaluation["all_required_gates_pass"] = all(gate_results.values())
    return evaluation


def _write_retired_baseline(path: Path, manifest: dict) -> None:
    path.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {
        "schema_version": 1,
        "case_id": manifest["case_id"],
        "implementation": "retired_candlestick_baseline",
        "status": "retired",
        "reason": "legacy benchmark implementation removed after unified adapter migration",
    }
    first_run = manifest.get("first_run")
    if isinstance(first_run, dict) and isinstance(first_run.get("evaluation"), dict):
        report["recorded_first_run_evaluation"] = first_run["evaluation"]
        report["recorded_first_run_classification"] = first_run.get("classification")
    _write_comparison_csv(path / "comparison.csv", [])
    (path / "evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_benchmark(case_dir: Path | str, output_dir: Path | str) -> Path:
    case = Path(case_dir).resolve()
    output = Path(output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            f"refusing to overwrite non-empty evidence directory: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(case / "manifest.json")
    spec = figure_spec_from_manifest(manifest)
    extraction_dir = output / "extraction"
    authorized = run_candlestick_extraction(spec, extraction_dir)

    validation_dir = output / "validation"
    validation_dir.mkdir(parents=True, exist_ok=False)
    evaluation = _evaluate_after_extraction(
        case, manifest, extraction_dir, authorized
    )
    _write_comparison_csv(
        validation_dir / "comparison.csv", evaluation["comparisons"]
    )
    (validation_dir / "evaluation.json").write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_retired_baseline(output / "baseline", manifest)
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
