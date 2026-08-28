"""Independent matching and metrics for candlestick extraction outputs."""

from __future__ import annotations

from functools import lru_cache
import math
from typing import Sequence


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
    rmse = math.sqrt(sum(error * error for error in errors) / count)
    return {
        "mae": mae,
        "rmse": rmse,
        "p95_absolute_error": absolute[p95_index],
        "max_absolute_error": absolute[-1],
        "normalized_mae": mae / price_range if price_range else None,
    }


def evaluate_ohlc(
    detected_rows: Sequence[dict],
    truth_rows: Sequence[dict],
    tolerance_px: float,
    price_range: float | None = None,
) -> dict:
    matches, extras, missing = monotonic_match(detected_rows, truth_rows, tolerance_px)
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
            "x_error_px": _number(detected, "x_center") - _number(truth, "x_center_px"),
        }
        for field in fields:
            error = _number(detected, field) - _number(truth, field)
            field_errors[field].append(error)
            row[f"detected_{field}"] = _number(detected, field)
            row[f"truth_{field}"] = _number(truth, field)
            row[f"{field}_error"] = error
            row[f"{field}_absolute_error"] = abs(error)
        if (
            _number(detected, "high") < max(_number(detected, "open"), _number(detected, "close"))
            or _number(detected, "low") > min(_number(detected, "open"), _number(detected, "close"))
        ):
            invariant_violations += 1
        comparisons.append(row)

    matched_count = len(matches)
    precision = matched_count / len(detected_rows) if detected_rows else 0.0
    recall = matched_count / len(truth_rows) if truth_rows else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    unsafe_false_accepts = sum(
        1 for index in extras if detected_rows[index].get("confidence") == "high"
    )
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
            field: _field_metrics(field_errors[field], price_range) for field in fields
        },
        "comparisons": comparisons,
        "ohlc_invariant_violation_count": invariant_violations,
        "unsafe_false_accept_count": unsafe_false_accepts,
    }
