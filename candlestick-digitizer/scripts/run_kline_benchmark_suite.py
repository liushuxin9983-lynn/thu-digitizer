"""Run every candlestick benchmark case in a suite and retain complete summaries."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import time

from run_kline_benchmark import run_benchmark


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _mean(values: list[float]) -> float | None:
    finite = [value for value in values if math.isfinite(value)]
    return sum(finite) / len(finite) if finite else None


def _record_from_evaluation(item: dict, evaluation: dict, elapsed: float) -> dict:
    normalized = {
        field: metrics.get("normalized_mae")
        for field, metrics in evaluation.get("fields", {}).items()
    }
    return {
        "case_id": item["case_id"],
        "family": item.get("family"),
        "classification": item.get("classification"),
        "status": "completed",
        "elapsed_seconds": round(elapsed, 6),
        "detected_count": evaluation.get("detected_count", 0),
        "truth_count": evaluation.get("truth_count", 0),
        "matched_count": evaluation.get("matched_count", 0),
        "missing_count": len(evaluation.get("missing_truth_indices", [])),
        "extra_count": len(evaluation.get("extra_detected_indices", [])),
        "precision": evaluation.get("precision"),
        "recall": evaluation.get("recall"),
        "f1": evaluation.get("f1"),
        "normalized_mae": normalized,
        "max_absolute_error": max(
            (
                metrics["max_absolute_error"]
                for metrics in evaluation.get("fields", {}).values()
                if metrics.get("max_absolute_error") is not None
            ),
            default=None,
        ),
        "unsafe_false_accept_count": evaluation.get("unsafe_false_accept_count", 0),
    }


def _write_csv(path: Path, records: list[dict]) -> None:
    fieldnames = [
        "case_id", "family", "classification", "status", "elapsed_seconds",
        "detected_count", "truth_count", "matched_count", "missing_count", "extra_count",
        "precision", "recall", "f1", "open_normalized_mae", "high_normalized_mae",
        "low_normalized_mae", "close_normalized_mae", "max_absolute_error",
        "unsafe_false_accept_count", "warning", "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            normalized = record.get("normalized_mae", {})
            writer.writerow(
                {
                    **{key: record.get(key) for key in fieldnames},
                    "open_normalized_mae": normalized.get("open"),
                    "high_normalized_mae": normalized.get("high"),
                    "low_normalized_mae": normalized.get("low"),
                    "close_normalized_mae": normalized.get("close"),
                }
            )


def compare_suite_summaries(current: dict, baseline: dict) -> dict:
    """Return paired precision/recall/F1 deltas without mutating either summary."""
    baseline_cases = {record["case_id"]: record for record in baseline.get("cases", [])}
    current_case_ids = {record["case_id"] for record in current.get("cases", [])}
    if current_case_ids != set(baseline_cases):
        missing = sorted(set(baseline_cases) - current_case_ids)
        extra = sorted(current_case_ids - set(baseline_cases))
        raise ValueError(
            f"paired suite inventory mismatch: missing={missing}, extra={extra}"
        )
    comparisons = []
    for record in current.get("cases", []):
        previous = baseline_cases.get(record["case_id"])
        if previous is None:
            continue
        comparison = {"case_id": record["case_id"]}
        for field in ["precision", "recall", "f1"]:
            current_value = record.get(field)
            baseline_value = previous.get(field)
            comparison[f"{field}_delta"] = (
                current_value - baseline_value
                if current_value is not None and baseline_value is not None
                else None
            )
        comparisons.append(comparison)
    macro_delta = {}
    for field in ["precision", "recall", "f1"]:
        current_value = current.get("macro", {}).get(field)
        baseline_value = baseline.get("macro", {}).get(field)
        macro_delta[field] = (
            current_value - baseline_value
            if current_value is not None and baseline_value is not None
            else None
        )
    return {
        "baseline_suite_id": baseline.get("suite_id"),
        "current_suite_id": current.get("suite_id"),
        "macro_delta": macro_delta,
        "cases": comparisons,
    }


def run_suite(
    suite_dir: Path | str,
    output_dir: Path | str,
    baseline_summary: Path | str | None = None,
) -> Path:
    suite_root = Path(suite_dir).resolve()
    output = Path(output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty evidence directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    cases_output = output / "cases"
    cases_output.mkdir()
    suite = _read_json(suite_root / "suite.json")
    records: list[dict] = []

    for item in suite.get("cases", []):
        started = time.perf_counter()
        case_output = cases_output / item["case_id"]
        warning = None
        error = None
        try:
            run_benchmark(suite_root / item["path"], case_output)
        except Exception as exc:  # Preserve case evidence and continue the benchmark inventory.
            error = f"{type(exc).__name__}: {exc}"
        elapsed = time.perf_counter() - started
        evaluation_path = case_output / "validation" / "evaluation.json"
        if evaluation_path.exists():
            record = _record_from_evaluation(item, _read_json(evaluation_path), elapsed)
            if error:
                warning = f"post_validation_error: {error}"
        else:
            record = {
                "case_id": item["case_id"],
                "family": item.get("family"),
                "classification": item.get("classification"),
                "status": "failed",
                "elapsed_seconds": round(elapsed, 6),
                "error": error or "evaluation report missing",
            }
        if warning:
            record["warning"] = warning
        records.append(record)

    completed = [record for record in records if record["status"] == "completed"]
    failed = [record for record in records if record["status"] == "failed"]
    summary = {
        "schema_version": 1,
        "suite_id": suite.get("suite_id"),
        "source_suite": str(suite_root),
        "case_count": len(records),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "macro": {
            "precision": _mean([record["precision"] for record in completed]),
            "recall": _mean([record["recall"] for record in completed]),
            "f1": _mean([record["f1"] for record in completed]),
            "normalized_mae": {
                field: _mean(
                    [
                        record["normalized_mae"][field]
                        for record in completed
                        if record["normalized_mae"].get(field) is not None
                    ]
                )
                for field in ["open", "high", "low", "close"]
            },
        },
        "totals": {
            key: sum(int(record.get(key, 0)) for record in completed)
            for key in ["detected_count", "truth_count", "matched_count", "missing_count", "extra_count", "unsafe_false_accept_count"]
        },
        "cases": records,
    }
    if baseline_summary is not None:
        baseline_path = Path(baseline_summary).resolve()
        baseline = _read_json(baseline_path)
        summary["comparison_to_baseline"] = {
            "baseline_summary": str(baseline_path),
            **compare_suite_summaries(summary, baseline),
        }
    (output / "suite-evaluation.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(output / "suite-comparison.csv", records)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-summary", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output = run_suite(args.suite_dir, args.output_dir, args.baseline_summary)
    print(f"SUITE_EVIDENCE={output}")


if __name__ == "__main__":
    main()
