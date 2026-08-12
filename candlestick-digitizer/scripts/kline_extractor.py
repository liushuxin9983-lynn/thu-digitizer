"""Evidence-bound candidate extraction primitives for candlestick charts."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict
import csv
import hashlib
import json
import math
from numbers import Integral
from numbers import Real
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image
from PIL import ImageDraw


class ExtractionRefused(ValueError):
    """Raised when numeric extraction cannot satisfy a hard evidence contract."""

    def __init__(self, reason_code: str, details: dict | None = None):
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.details = _json_safe(details) if details is not None else None


@dataclass(frozen=True)
class PriceAnchorVerification:
    declared_pixel: int
    value: float
    verified_pixel: int | None
    evidence: dict
    support_ratio: float
    pixel_adjustment: int | None
    status: str
    reason_code: str | None


PRICE_AXIS_ANCHOR_EVIDENCE_REASON_CODES = frozenset(
    {
        "price_axis_anchor_evidence_required",
        "invalid_price_axis_anchor_evidence",
        "unsupported_price_axis_anchor_evidence",
        "price_axis_anchor_evidence_out_of_bounds",
        "price_axis_anchor_evidence_insufficient_support",
    }
)


def _is_finite_integer(value: object) -> bool:
    return isinstance(value, Integral) and not isinstance(value, bool)


def _finite_real_or_none(value: object) -> float | None:
    if not isinstance(value, Real) or isinstance(value, bool):
        return None
    try:
        numeric_value = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return numeric_value if math.isfinite(numeric_value) else None


def _is_finite_real(value: object) -> bool:
    return _finite_real_or_none(value) is not None


def _json_safe(value: object, depth: int = 0) -> object:
    """Bound malformed refusal details to JSON-serializable diagnostic values."""
    if depth >= 8:
        return "<maximum detail depth>"
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value if len(value) <= 256 else f"{value[:256]}...<truncated>"
    if isinstance(value, int):
        if value.bit_length() <= 1024:
            return value
        return {"type": "oversized_integer", "bits": value.bit_length()}
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.generic):
        return _json_safe(value.item(), depth + 1)
    if isinstance(value, dict):
        return {
            key if isinstance(key, str) else f"<{type(key).__name__}>": _json_safe(
                item, depth + 1
            )
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item, depth + 1) for item in list(value)[:100]]
    return f"<{type(value).__name__}>"


def verify_price_anchor_evidence(
    pixels: np.ndarray,
    declared_pixel: object,
    value: object,
    evidence: object,
) -> PriceAnchorVerification:
    """Verify a declared price anchor against a horizontal source-pixel segment."""

    try:
        safe_declared_pixel = int(declared_pixel) if _is_finite_integer(declared_pixel) else 0
    except (OverflowError, TypeError, ValueError):
        safe_declared_pixel = 0
    finite_value = _finite_real_or_none(value)
    safe_value = finite_value if finite_value is not None else 0.0
    safe_evidence = _json_safe(evidence) if isinstance(evidence, dict) else {}

    def refuse(
        reason_code: str,
        *,
        support_ratio: float = 0.0,
    ) -> None:
        failed = PriceAnchorVerification(
            declared_pixel=safe_declared_pixel,
            value=safe_value,
            verified_pixel=None,
            evidence=safe_evidence,
            support_ratio=support_ratio,
            pixel_adjustment=None,
            status="refused",
            reason_code=reason_code,
        )
        raise ExtractionRefused(reason_code, details=asdict(failed))

    if (
        not isinstance(pixels, np.ndarray)
        or pixels.ndim != 3
        or pixels.shape[2] != 3
        or not np.issubdtype(pixels.dtype, np.number)
        or np.issubdtype(pixels.dtype, np.complexfloating)
        or np.issubdtype(pixels.dtype, np.bool_)
    ):
        refuse("invalid_price_axis_anchor_evidence")
    try:
        if not np.isfinite(pixels).all():
            refuse("invalid_price_axis_anchor_evidence")
    except (TypeError, ValueError):
        refuse("invalid_price_axis_anchor_evidence")
    height, width, _ = pixels.shape

    if not _is_finite_integer(declared_pixel) or finite_value is None:
        refuse("invalid_price_axis_anchor_evidence")
    try:
        declared = int(declared_pixel)
    except (OverflowError, TypeError, ValueError):
        refuse("invalid_price_axis_anchor_evidence")
    numeric_value = finite_value

    if not isinstance(evidence, dict):
        refuse("invalid_price_axis_anchor_evidence")
    if evidence.get("kind") != "horizontal_reference_line":
        refuse("unsupported_price_axis_anchor_evidence")
    if evidence.get("role") not in {"gridline", "axis_tick"}:
        refuse("unsupported_price_axis_anchor_evidence")

    x_range = evidence.get("x_range")
    if (
        not isinstance(x_range, (list, tuple))
        or len(x_range) != 2
        or not all(_is_finite_integer(item) for item in x_range)
    ):
        refuse("invalid_price_axis_anchor_evidence")
    try:
        x0, x1 = (int(item) for item in x_range)
    except (OverflowError, TypeError, ValueError):
        refuse("invalid_price_axis_anchor_evidence")
    if x0 > x1:
        refuse("invalid_price_axis_anchor_evidence")

    color = evidence.get("color")
    if not isinstance(color, str) or len(color) != 7 or not color.startswith("#"):
        refuse("invalid_price_axis_anchor_evidence")
    try:
        target = parse_hex_color(color)
    except ExtractionRefused:
        refuse("invalid_price_axis_anchor_evidence")

    tolerance = evidence.get("tolerance")
    min_support_ratio = evidence.get("min_support_ratio")
    max_row_offset_px = evidence.get("max_row_offset_px")
    finite_tolerance = _finite_real_or_none(tolerance)
    finite_min_support_ratio = _finite_real_or_none(min_support_ratio)
    if (
        finite_tolerance is None
        or finite_tolerance < 0
        or finite_min_support_ratio is None
        or not 0 < finite_min_support_ratio <= 1
        or not _is_finite_integer(max_row_offset_px)
    ):
        refuse("invalid_price_axis_anchor_evidence")
    try:
        row_offset = int(max_row_offset_px)
    except (OverflowError, TypeError, ValueError):
        refuse("invalid_price_axis_anchor_evidence")
    if row_offset < 0:
        refuse("invalid_price_axis_anchor_evidence")

    if x0 < 0 or x1 >= width or declared < 0 or declared >= height:
        refuse("price_axis_anchor_evidence_out_of_bounds")
    if declared - row_offset < 0 or declared + row_offset >= height:
        refuse("price_axis_anchor_evidence_out_of_bounds")

    target_rgb = np.asarray(target, dtype=np.float64)
    candidates: list[tuple[float, int]] = []
    for row in range(declared - row_offset, declared + row_offset + 1):
        segment = pixels[row, x0 : x1 + 1].astype(np.float64, copy=False)
        distances = np.sqrt(np.square(segment - target_rgb).sum(axis=1))
        support = float((distances <= finite_tolerance).mean())
        candidates.append((support, row))
    best_support, best_row = min(
        candidates,
        key=lambda candidate: (-candidate[0], abs(candidate[1] - declared), candidate[1]),
    )
    if best_support < finite_min_support_ratio:
        refuse(
            "price_axis_anchor_evidence_insufficient_support",
            support_ratio=best_support,
        )

    return PriceAnchorVerification(
        declared_pixel=declared,
        value=numeric_value,
        verified_pixel=best_row,
        evidence=dict(evidence),
        support_ratio=best_support,
        pixel_adjustment=best_row - declared,
        status="verified",
        reason_code=None,
    )


def _declared_price_axis_anchors(
    axis: dict,
    image_height: int,
) -> list[tuple[int, float]]:
    anchors = axis.get("anchors")
    if (
        not isinstance(anchors, (list, tuple))
        or len(anchors) != 2
        or not all(isinstance(anchor, dict) for anchor in anchors)
    ):
        raise ExtractionRefused("price_axis_requires_two_anchors")
    declared: list[tuple[int, float]] = []
    for anchor in anchors:
        pixel = anchor.get("pixel")
        value = _finite_real_or_none(anchor.get("value"))
        if (
            not _is_finite_integer(pixel)
            or not 0 <= int(pixel) < image_height
            or value is None
        ):
            raise ExtractionRefused("invalid_price_axis_anchor")
        declared.append((int(pixel), value))
    return declared


def verify_price_axis_anchors(
    pixels: np.ndarray,
    axis: dict,
) -> tuple[list[tuple[float, float]], list[dict]]:
    """Return calibration anchors and complete source-evidence records."""

    declared = _declared_price_axis_anchors(axis, pixels.shape[0])
    require_anchor_evidence = axis.get("require_anchor_evidence", False)
    if not isinstance(require_anchor_evidence, bool):
        raise ExtractionRefused("invalid_price_axis_anchor")
    if require_anchor_evidence is False:
        return declared, []

    verified: list[tuple[float, float]] = []
    records: list[dict] = []
    for anchor, (declared_pixel, value) in zip(axis["anchors"], declared):
        if "evidence" not in anchor:
            finite_value = _finite_real_or_none(value)
            failed = PriceAnchorVerification(
                declared_pixel=(
                    int(declared_pixel) if _is_finite_integer(declared_pixel) else 0
                ),
                value=finite_value if finite_value is not None else 0.0,
                verified_pixel=None,
                evidence={},
                support_ratio=0.0,
                pixel_adjustment=None,
                status="refused",
                reason_code="price_axis_anchor_evidence_required",
            )
            records.append(asdict(failed))
            raise ExtractionRefused(
                "price_axis_anchor_evidence_required",
                details={"anchor_verifications": records},
            )
        try:
            verification = verify_price_anchor_evidence(
                pixels,
                declared_pixel=declared_pixel,
                value=value,
                evidence=anchor["evidence"],
            )
        except ExtractionRefused as exc:
            if exc.reason_code not in PRICE_AXIS_ANCHOR_EVIDENCE_REASON_CODES:
                raise
            if isinstance(exc.details, dict):
                records.append(exc.details)
            raise ExtractionRefused(
                exc.reason_code,
                details={"anchor_verifications": records},
            ) from exc
        record = asdict(verification)
        records.append(record)
        verified.append((float(verification.verified_pixel), verification.value))
    return verified, records


@dataclass(frozen=True)
class SourceContract:
    sha256: str
    width: int
    height: int

    @classmethod
    def from_path(cls, path: Path | str) -> "SourceContract":
        source = Path(path)
        digest = hashlib.sha256(source.read_bytes()).hexdigest().upper()
        with Image.open(source) as image:
            width, height = image.size
        return cls(sha256=digest, width=width, height=height)


def validate_source_contract(path: Path | str, expected: SourceContract) -> SourceContract:
    actual = SourceContract.from_path(path)
    if actual != expected:
        raise ExtractionRefused("source_contract_mismatch")
    return actual


@dataclass(frozen=True)
class LinearPriceCalibration:
    slope: float
    intercept: float
    anchors: tuple[tuple[float, float], tuple[float, float]]

    @classmethod
    def from_anchors(
        cls, anchors: Iterable[tuple[float, float]]
    ) -> "LinearPriceCalibration":
        points = tuple((float(pixel), float(value)) for pixel, value in anchors)
        if len(points) != 2:
            raise ExtractionRefused("price_axis_requires_two_anchors")
        (y1, value1), (y2, value2) = points
        if y1 == y2:
            raise ExtractionRefused("degenerate_price_axis")
        slope = (value2 - value1) / (y2 - y1)
        return cls(slope=slope, intercept=value1 - slope * y1, anchors=points)

    def value_at(self, y_px: float) -> float:
        return self.intercept + self.slope * float(y_px)


@dataclass(frozen=True)
class BodyOcclusionBridge:
    upper_fragment: tuple[int, int, int, int]
    lower_fragment: tuple[int, int, int, int]
    gap_top: int
    gap_bottom: int
    occluder_row_coverage: float
    occluder_role: str


@dataclass(frozen=True)
class BodyCandidate:
    style_id: str
    kind: str
    left: int
    right: int
    top: int
    bottom: int
    center: float
    evidence_score: float
    status: str
    reason_code: str | None = None
    occlusion_bridges: tuple[BodyOcclusionBridge, ...] = ()


@dataclass(frozen=True)
class OutlineConfig:
    style_id: str
    min_width: int
    max_width: int
    min_vertical_length: int = 4
    horizontal_support: float = 0.65
    edge_y_tolerance: int = 3


@dataclass(frozen=True)
class FilledConfig:
    style_id: str
    min_width: int
    max_width: int
    min_body_height: int = 2
    center_tolerance: float = 3.0
    width_tolerance: int = 6


@dataclass(frozen=True)
class FilledBodyBridgeConfig:
    enabled: bool = False
    max_gap: int = 8
    max_center_delta: float = 2.0
    max_edge_delta: int = 3
    max_width_delta: int = 4
    max_union_width: int = 0
    min_horizontal_overlap: int = 1
    occluder_vertical_radius: int = 0
    min_occluder_row_coverage: float = 1.0
    min_color_separation: float = 1.0
    occluder_role: str = "topology_only_not_numeric_fill"

    def __post_init__(self) -> None:
        nonnegative = {
            "max_gap": self.max_gap,
            "max_center_delta": self.max_center_delta,
            "max_edge_delta": self.max_edge_delta,
            "max_width_delta": self.max_width_delta,
            "max_union_width": self.max_union_width,
            "occluder_vertical_radius": self.occluder_vertical_radius,
        }
        if any(
            not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
            for value in nonnegative.values()
        ):
            raise ExtractionRefused("invalid_body_bridge_config")
        if self.min_horizontal_overlap < 1:
            raise ExtractionRefused("invalid_body_bridge_config")
        if self.enabled and self.max_union_width < self.min_horizontal_overlap:
            raise ExtractionRefused("invalid_body_bridge_config")
        if self.occluder_vertical_radius not in (0, 1):
            raise ExtractionRefused("invalid_body_bridge_config")
        if (
            not math.isfinite(float(self.min_occluder_row_coverage))
            or not 0 <= self.min_occluder_row_coverage <= 1
        ):
            raise ExtractionRefused("invalid_body_bridge_config")
        if (
            not math.isfinite(float(self.min_color_separation))
            or self.min_color_separation <= 0
        ):
            raise ExtractionRefused("invalid_body_bridge_config")


def occluder_colors_are_separable(
    candle_colors: Iterable[tuple[int, int, int]],
    candle_tolerance: float,
    occluder_colors: Iterable[tuple[int, int, int]],
    occluder_tolerance: float,
    minimum_ratio: float,
) -> bool:
    """Return whether every candle/occluder colour pair has disjoint tolerance balls."""
    candles = tuple(candle_colors)
    occluders = tuple(occluder_colors)
    if (
        not candles
        or not occluders
        or not math.isfinite(float(candle_tolerance))
        or not math.isfinite(float(occluder_tolerance))
        or not math.isfinite(float(minimum_ratio))
        or candle_tolerance < 0
        or occluder_tolerance < 0
        or minimum_ratio <= 0
    ):
        return False
    required = minimum_ratio * (float(candle_tolerance) + float(occluder_tolerance))
    return all(
        math.dist(candle, occluder) >= required
        for candle in candles
        for occluder in occluders
    )


@dataclass(frozen=True)
class WickCandidate:
    top: int
    bottom: int
    status: str
    reason_code: str | None = None


@dataclass(frozen=True)
class CandleCandidate:
    body: BodyCandidate
    wick: WickCandidate
    direction: str


@dataclass(frozen=True)
class ExtractedCandle:
    x_center: float
    style_id: str
    direction: str
    open: float
    high: float
    low: float
    close: float
    y_body_top: int
    y_body_bottom: int
    y_wick_top: int
    y_wick_bottom: int
    body_left: int
    body_right: int
    confidence: str


@dataclass(frozen=True)
class CoverageRecord:
    x_center: float
    status: str
    reason_code: str | None


@dataclass(frozen=True)
class ExtractionResult:
    candles: tuple[ExtractedCandle, ...]
    candidates: tuple[CandleCandidate, ...]
    coverage_ledger: tuple[CoverageRecord, ...]
    numeric_output_authorized: bool


def _true_runs(values: np.ndarray) -> list[tuple[int, int]]:
    indices = np.flatnonzero(values)
    if indices.size == 0:
        return []
    split_at = np.flatnonzero(np.diff(indices) > 1) + 1
    chunks = np.split(indices, split_at)
    return [(int(chunk[0]), int(chunk[-1])) for chunk in chunks]


def _longest_true_run(values: np.ndarray) -> tuple[int, int] | None:
    runs = _true_runs(values)
    return max(runs, key=lambda run: run[1] - run[0] + 1) if runs else None


def detect_outline_bodies(
    mask: np.ndarray,
    plot_bounds: tuple[int, int, int, int],
    config: OutlineConfig,
) -> list[BodyCandidate]:
    """Pair horizontal outline edges and retain unmatched vertical evidence."""
    x0, y0, x1, y1 = plot_bounds
    horizontal_groups: list[list[dict[str, int]]] = []
    for y in range(y0, y1 + 1):
        for local_left, local_right in _true_runs(mask[y, x0 : x1 + 1]):
            left, right = local_left + x0, local_right + x0
            width = right - left
            if not (config.min_width <= width <= config.max_width):
                continue
            run = {"y": y, "left": left, "right": right}
            matching_group = None
            for group in reversed(horizontal_groups):
                previous = group[-1]
                if (
                    y - previous["y"] <= 1
                    and abs(left - previous["left"]) <= config.edge_y_tolerance
                    and abs(right - previous["right"]) <= config.edge_y_tolerance
                ):
                    matching_group = group
                    break
            if matching_group is None:
                horizontal_groups.append([run])
            else:
                matching_group.append(run)

    horizontal_edges = [
        {
            "y": int(round(float(np.median([run["y"] for run in group])))),
            "left": int(round(float(np.median([run["left"] for run in group])))),
            "right": int(round(float(np.median([run["right"] for run in group])))),
        }
        for group in horizontal_groups
    ]
    horizontal_edges.sort(key=lambda edge: (edge["left"], edge["y"]))

    results: list[BodyCandidate] = []
    paired_horizontal: set[int] = set()
    for top_index, top_edge in enumerate(horizontal_edges):
        if top_index in paired_horizontal:
            continue
        best: tuple[float, int, dict[str, int]] | None = None
        for bottom_index in range(top_index + 1, len(horizontal_edges)):
            if bottom_index in paired_horizontal:
                continue
            bottom_edge = horizontal_edges[bottom_index]
            if bottom_edge["y"] <= top_edge["y"]:
                continue
            if abs(top_edge["left"] - bottom_edge["left"]) > config.edge_y_tolerance:
                continue
            if abs(top_edge["right"] - bottom_edge["right"]) > config.edge_y_tolerance:
                continue
            left = round((top_edge["left"] + bottom_edge["left"]) / 2)
            right = round((top_edge["right"] + bottom_edge["right"]) / 2)
            top, bottom = top_edge["y"], bottom_edge["y"]
            side_height = bottom - top + 1
            left_support = float(mask[top : bottom + 1, max(x0, left - 1) : left + 2].any(axis=1).mean())
            right_support = float(mask[top : bottom + 1, right : min(x1 + 1, right + 2)].any(axis=1).mean())
            support = min(left_support, right_support)
            if support < 0.2:
                continue
            score = support
            if best is None or score > best[0]:
                best = (score, bottom_index, bottom_edge)
        if best is None:
            continue
        score, bottom_index, bottom_edge = best
        paired_horizontal.update({top_index, bottom_index})
        left = round((top_edge["left"] + bottom_edge["left"]) / 2)
        right = round((top_edge["right"] + bottom_edge["right"]) / 2)
        results.append(
            BodyCandidate(
                style_id=config.style_id,
                kind="outline",
                left=left,
                right=right,
                top=top_edge["y"],
                bottom=bottom_edge["y"],
                center=(left + right) / 2,
                evidence_score=score,
                status="candidate",
            )
        )

    vertical_edges: list[dict[str, int]] = []
    for x in range(x0, x1 + 1):
        run = _longest_true_run(mask[y0 : y1 + 1, x])
        if run is None:
            continue
        top, bottom = run[0] + y0, run[1] + y0
        if bottom - top + 1 >= config.min_vertical_length:
            vertical_edges.append({"x": x, "top": top, "bottom": bottom})

    fallback_edges = [
        edge
        for edge in vertical_edges
        if not any(body.left <= edge["x"] <= body.right for body in results)
    ]
    used_fallback: set[int] = set()
    for left_index, left_edge in enumerate(fallback_edges):
        if left_index in used_fallback:
            continue
        for right_index in range(left_index + 1, len(fallback_edges)):
            if right_index in used_fallback:
                continue
            right_edge = fallback_edges[right_index]
            width = right_edge["x"] - left_edge["x"]
            if width < config.min_width:
                continue
            if width > config.max_width:
                break
            if abs(left_edge["top"] - right_edge["top"]) > config.edge_y_tolerance:
                continue
            if abs(left_edge["bottom"] - right_edge["bottom"]) > config.edge_y_tolerance:
                continue
            top = round((left_edge["top"] + right_edge["top"]) / 2)
            bottom = round((left_edge["bottom"] + right_edge["bottom"]) / 2)
            top_support = float(mask[top, left_edge["x"] : right_edge["x"] + 1].mean())
            bottom_support = float(mask[bottom, left_edge["x"] : right_edge["x"] + 1].mean())
            support = min(top_support, bottom_support)
            if support < config.horizontal_support:
                continue
            used_fallback.update({left_index, right_index})
            results.append(
                BodyCandidate(
                    style_id=config.style_id,
                    kind="outline",
                    left=left_edge["x"],
                    right=right_edge["x"],
                    top=top,
                    bottom=bottom,
                    center=(left_edge["x"] + right_edge["x"]) / 2,
                    evidence_score=support,
                    status="candidate",
                )
            )
            break

    for edge in vertical_edges:
        if any(body.left <= edge["x"] <= body.right for body in results):
            continue
        results.append(
            BodyCandidate(
                style_id=config.style_id,
                kind="outline",
                left=edge["x"],
                right=edge["x"],
                top=edge["top"],
                bottom=edge["bottom"],
                center=float(edge["x"]),
                evidence_score=0.0,
                status="ambiguous_body",
                reason_code="unpaired_outline_edge",
            )
        )
    return sorted(results, key=lambda candidate: candidate.center)


def detect_filled_bodies(
    mask: np.ndarray,
    plot_bounds: tuple[int, int, int, int],
    config: FilledConfig,
) -> list[BodyCandidate]:
    """Detect filled bodies from repeated horizontal width support."""
    x0, y0, x1, y1 = plot_bounds
    row_runs: list[dict[str, float | int]] = []
    for y in range(y0, y1 + 1):
        for local_left, local_right in _true_runs(mask[y, x0 : x1 + 1]):
            left, right = local_left + x0, local_right + x0
            width = right - left + 1
            if config.min_width <= width <= config.max_width:
                row_runs.append(
                    {
                        "y": y,
                        "left": left,
                        "right": right,
                        "width": width,
                        "center": (left + right) / 2,
                    }
                )

    groups: list[list[dict[str, float | int]]] = []
    for run in row_runs:
        match = None
        for group in reversed(groups):
            previous = group[-1]
            if (
                int(run["y"]) == int(previous["y"]) + 1
                and abs(float(run["center"]) - float(previous["center"]))
                <= config.center_tolerance
                and abs(int(run["width"]) - int(previous["width"]))
                <= config.width_tolerance
            ):
                match = group
                break
        if match is None:
            groups.append([run])
        else:
            match.append(run)

    candidates: list[BodyCandidate] = []
    for group in groups:
        if len(group) < config.min_body_height:
            continue
        left = int(round(float(np.median([row["left"] for row in group]))))
        right = int(round(float(np.median([row["right"] for row in group]))))
        top = int(group[0]["y"])
        bottom = int(group[-1]["y"])
        candidates.append(
            BodyCandidate(
                style_id=config.style_id,
                kind="filled",
                left=left,
                right=right,
                top=top,
                bottom=bottom,
                center=(left + right) / 2,
                evidence_score=float(len(group) * (right - left + 1)),
                status="candidate",
            )
        )
    return sorted(candidates, key=lambda candidate: candidate.center)


def merge_occluded_filled_body_fragments(
    fragments: Iterable[BodyCandidate],
    occluder_mask: np.ndarray,
    config: FilledBodyBridgeConfig,
) -> list[BodyCandidate]:
    """Merge uniquely aligned filled-body fragments across verified overlay rows."""
    ordered = sorted(fragments, key=lambda body: (body.top, body.center))
    if not config.enabled or len(ordered) < 2:
        return sorted(ordered, key=lambda body: body.center)

    edges: list[tuple[int, int, BodyOcclusionBridge]] = []
    outgoing: dict[int, list[int]] = {index: [] for index in range(len(ordered))}
    incoming: dict[int, list[int]] = {index: [] for index in range(len(ordered))}
    for upper_index, upper in enumerate(ordered):
        for lower_index, lower in enumerate(ordered):
            if lower.top <= upper.bottom:
                continue
            if upper.style_id != lower.style_id or upper.kind != lower.kind:
                continue
            gap_top, gap_bottom = upper.bottom + 1, lower.top - 1
            gap = gap_bottom - gap_top + 1
            if not (1 <= gap <= config.max_gap):
                continue
            overlap_left = max(upper.left, lower.left)
            overlap_right = min(upper.right, lower.right)
            if overlap_left > overlap_right:
                continue
            overlap_width = overlap_right - overlap_left + 1
            strict_alignment = (
                abs(upper.center - lower.center) <= config.max_center_delta
                and abs(upper.left - lower.left) <= config.max_edge_delta
                and abs(upper.right - lower.right) <= config.max_edge_delta
                and abs((upper.right - upper.left) - (lower.right - lower.left))
                <= config.max_width_delta
            )
            union_width = max(upper.right, lower.right) - min(upper.left, lower.left) + 1
            if not strict_alignment:
                continue
            if config.max_union_width > 0 and (
                union_width > config.max_union_width
                or overlap_width < config.min_horizontal_overlap
            ):
                continue
            radius = max(0, config.occluder_vertical_radius)
            direct_rows = occluder_mask[
                gap_top : gap_bottom + 1,
                overlap_left : overlap_right + 1,
            ].any(axis=1)
            if not direct_rows.any():
                continue
            rows = np.asarray(
                [
                    occluder_mask[
                        max(0, y - radius) : min(occluder_mask.shape[0], y + radius + 1),
                        overlap_left : overlap_right + 1,
                    ].any()
                    for y in range(gap_top, gap_bottom + 1)
                ],
                dtype=bool,
            )
            coverage = float(rows.mean()) if rows.size else 0.0
            if coverage < config.min_occluder_row_coverage:
                continue
            bridge = BodyOcclusionBridge(
                upper_fragment=(upper.left, upper.right, upper.top, upper.bottom),
                lower_fragment=(lower.left, lower.right, lower.top, lower.bottom),
                gap_top=gap_top,
                gap_bottom=gap_bottom,
                occluder_row_coverage=coverage,
                occluder_role=config.occluder_role,
            )
            edge_index = len(edges)
            edges.append((upper_index, lower_index, bridge))
            outgoing[upper_index].append(edge_index)
            incoming[lower_index].append(edge_index)

    safe_edges = [
        edge
        for edge_index, edge in enumerate(edges)
        if len(outgoing[edge[0]]) == 1 and len(incoming[edge[1]]) == 1
    ]
    parent = list(range(len(ordered)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    for upper_index, lower_index, _ in safe_edges:
        union(upper_index, lower_index)

    components: dict[int, list[int]] = {}
    for index in range(len(ordered)):
        components.setdefault(find(index), []).append(index)
    bridge_by_component: dict[int, list[BodyOcclusionBridge]] = {}
    for upper_index, _, bridge in safe_edges:
        bridge_by_component.setdefault(find(upper_index), []).append(bridge)

    merged: list[BodyCandidate] = []
    for root, indices in components.items():
        bodies = [ordered[index] for index in indices]
        if len(bodies) == 1:
            merged.append(bodies[0])
            continue
        left = min(body.left for body in bodies)
        right = max(body.right for body in bodies)
        if config.max_union_width > 0 and right - left + 1 > config.max_union_width:
            merged.extend(bodies)
            continue
        merged.append(
            BodyCandidate(
                style_id=bodies[0].style_id,
                kind=bodies[0].kind,
                left=left,
                right=right,
                top=min(body.top for body in bodies),
                bottom=max(body.bottom for body in bodies),
                center=(left + right) / 2,
                evidence_score=sum(body.evidence_score for body in bodies),
                status="candidate",
                occlusion_bridges=tuple(
                    sorted(bridge_by_component.get(root, []), key=lambda item: item.gap_top)
                ),
            )
        )
    return sorted(merged, key=lambda body: body.center)


def measure_wick(
    mask: np.ndarray,
    body: BodyCandidate,
    max_center_offset: int = 2,
    max_connection_gap: int = 1,
    occluder_mask: np.ndarray | None = None,
    max_occlusion_gap: int = 0,
    min_occluder_row_coverage: float = 0.5,
) -> WickCandidate:
    """Measure the narrow vertical run connected to an accepted body."""
    center = int(round(body.center))
    left = max(0, center - max_center_offset)
    right = min(mask.shape[1] - 1, center + max_center_offset)
    center_support = mask[:, left : right + 1].any(axis=1)
    runs = _true_runs(center_support)
    upper = [
        run
        for run in runs
        if run[0] <= body.top + max_connection_gap
        and run[1] >= body.top - max_connection_gap
    ]
    lower = [
        run
        for run in runs
        if run[0] <= body.bottom + max_connection_gap
        and run[1] >= body.bottom - max_connection_gap
    ]
    if not upper or not lower:
        return WickCandidate(
            top=body.top,
            bottom=body.bottom,
            status="ambiguous_wick",
            reason_code="center_wick_not_connected",
        )
    wick_top = min(run[0] for run in upper)
    wick_bottom = max(run[1] for run in lower)

    def verified_gap(gap_top: int, gap_bottom: int) -> bool:
        gap = gap_bottom - gap_top + 1
        if gap <= max_connection_gap:
            return True
        if occluder_mask is None or gap > max_occlusion_gap:
            return False
        rows = occluder_mask[
            gap_top : gap_bottom + 1,
            max(0, body.left) : min(mask.shape[1], body.right + 1),
        ].any(axis=1)
        return bool(rows.size and float(rows.mean()) >= min_occluder_row_coverage)

    for run_top, run_bottom in sorted(runs, reverse=True):
        if run_bottom >= wick_top:
            continue
        if verified_gap(run_bottom + 1, wick_top - 1):
            wick_top = run_top
    for run_top, run_bottom in sorted(runs):
        if run_top <= wick_bottom:
            continue
        if verified_gap(wick_bottom + 1, run_top - 1):
            wick_bottom = run_bottom

    return WickCandidate(top=wick_top, bottom=wick_bottom, status="candidate")


def assemble_extraction(
    candidates: Iterable[CandleCandidate],
    calibration: LinearPriceCalibration,
    duplicate_distance: float = 15.0,
) -> ExtractionResult:
    ordered = sorted(candidates, key=lambda candidate: candidate.body.center)
    duplicate_indices: set[int] = set()
    for index in range(1, len(ordered)):
        if ordered[index].body.center - ordered[index - 1].body.center < duplicate_distance:
            duplicate_indices.update({index - 1, index})

    candles: list[ExtractedCandle] = []
    ledger: list[CoverageRecord] = []
    for index, candidate in enumerate(ordered):
        body, wick = candidate.body, candidate.wick
        if index in duplicate_indices:
            ledger.append(
                CoverageRecord(body.center, "duplicate_candidate", "duplicate_candidate")
            )
            continue
        if body.status != "candidate":
            ledger.append(CoverageRecord(body.center, body.status, body.reason_code))
            continue
        if wick.status != "candidate":
            ledger.append(CoverageRecord(body.center, "ambiguous_wick", wick.reason_code))
            continue

        body_top_value = calibration.value_at(body.top)
        body_bottom_value = calibration.value_at(body.bottom)
        high = calibration.value_at(wick.top)
        low = calibration.value_at(wick.bottom)
        if candidate.direction == "close_above_open":
            open_value, close_value = body_bottom_value, body_top_value
        elif candidate.direction == "open_above_close":
            open_value, close_value = body_top_value, body_bottom_value
        else:
            ledger.append(
                CoverageRecord(body.center, "not_extracted", "unknown_style_direction")
            )
            continue
        if high < max(open_value, close_value) or low > min(open_value, close_value):
            ledger.append(CoverageRecord(body.center, "not_extracted", "ohlc_invariant_failed"))
            continue
        candles.append(
            ExtractedCandle(
                x_center=body.center,
                style_id=body.style_id,
                direction=candidate.direction,
                open=round(open_value, 6),
                high=round(high, 6),
                low=round(low, 6),
                close=round(close_value, 6),
                y_body_top=body.top,
                y_body_bottom=body.bottom,
                y_wick_top=wick.top,
                y_wick_bottom=wick.bottom,
                body_left=body.left,
                body_right=body.right,
                confidence="candidate",
            )
        )
        ledger.append(CoverageRecord(body.center, "extracted", None))

    authorized = bool(candles) and all(record.status == "extracted" for record in ledger)
    return ExtractionResult(
        candles=tuple(candles),
        candidates=tuple(ordered),
        coverage_ledger=tuple(ledger),
        numeric_output_authorized=authorized,
    )


def parse_hex_color(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) != 6:
        raise ExtractionRefused("invalid_color")
    try:
        return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError as exc:
        raise ExtractionRefused("invalid_color") from exc


def color_mask_multi(
    pixels: np.ndarray,
    colors: Iterable[tuple[int, int, int]],
    tolerance: float,
) -> np.ndarray:
    if not math.isfinite(float(tolerance)) or tolerance < 0:
        raise ExtractionRefused("invalid_color_tolerance")
    mask = np.zeros(pixels.shape[:2], dtype=bool)
    values = pixels.astype(np.int32)
    for color in colors:
        delta = values - np.asarray(color, dtype=np.int32)
        mask |= np.square(delta).sum(axis=2) <= tolerance * tolerance
    return mask


def extract_klines(
    image_path: Path | str,
    extraction_config: dict,
) -> tuple[ExtractionResult, dict]:
    """Run candidate extraction using configuration isolated from benchmark truth."""
    source_data = extraction_config.get("source_contract")
    if not source_data:
        raise ExtractionRefused("source_contract_required")
    expected = SourceContract(
        sha256=str(source_data["sha256"]).upper(),
        width=int(source_data["width"]),
        height=int(source_data["height"]),
    )
    actual = validate_source_contract(image_path, expected)
    bounds = tuple(int(value) for value in extraction_config["plot_bounds"])
    if len(bounds) != 4:
        raise ExtractionRefused("invalid_plot_bounds")
    x0, y0, x1, y1 = bounds
    if not (0 <= x0 < x1 < actual.width and 0 <= y0 < y1 < actual.height):
        raise ExtractionRefused("invalid_plot_bounds")

    with Image.open(image_path) as image:
        pixels = np.asarray(image.convert("RGB"))
    axis = extraction_config["price_axis"]
    if axis.get("scale") != "linear":
        raise ExtractionRefused("unsupported_price_axis")
    declared_anchors = _declared_price_axis_anchors(axis, pixels.shape[0])
    try:
        anchors, anchor_verifications = verify_price_axis_anchors(pixels, axis)
    except ExtractionRefused as exc:
        if exc.reason_code not in PRICE_AXIS_ANCHOR_EVIDENCE_REASON_CODES:
            raise
        details = exc.details if isinstance(exc.details, dict) else {}
        metadata = {
            "source_contract": asdict(actual),
            "coordinate_space": "original_raster_pixels",
            "plot_bounds": list(bounds),
            "price_axis": {
                "scale": "linear",
                "anchors": [list(point) for point in declared_anchors],
                "declared_anchors": [list(point) for point in declared_anchors],
                "calibrated_anchors": [],
                "anchor_verifications": details.get("anchor_verifications", []),
                "slope": None,
                "intercept": None,
            },
            "styles": extraction_config["styles"],
            "algorithm_version": (
                "candidate-v2"
                if any(
                    style.get("kind") == "filled"
                    and bool(
                        style.get("geometry", {}).get(
                            "bridge_filled_body_fragments", False
                        )
                    )
                    for style in extraction_config["styles"]
                )
                else "candidate-v1"
            ),
            "body_occluder_bridging": [],
            "refusal_reasons": [exc.reason_code],
        }
        return (
            ExtractionResult(
                candles=(),
                candidates=(),
                coverage_ledger=(),
                numeric_output_authorized=False,
            ),
            metadata,
        )
    calibration = LinearPriceCalibration.from_anchors(anchors)

    all_candidates: list[CandleCandidate] = []
    body_bridge_diagnostics: list[dict] = []
    body_bridge_requested = False
    for style in extraction_config["styles"]:
        colors = [parse_hex_color(value) for value in style["colors"]]
        mask = color_mask_multi(pixels, colors, float(style.get("tolerance", 12)))
        geometry = style.get("geometry", {})
        occluder_colors = [
            parse_hex_color(value) for value in geometry.get("verified_occluder_colors", [])
        ]
        occluder_mask = (
            color_mask_multi(
                pixels,
                occluder_colors,
                float(geometry.get("verified_occluder_tolerance", 12)),
            )
            if occluder_colors
            else None
        )
        min_width = int(geometry.get("min_body_width_px", 60))
        max_width = int(geometry.get("max_body_width_px", 120))
        if style["kind"] == "outline":
            bodies = detect_outline_bodies(
                mask,
                bounds,
                OutlineConfig(
                    style_id=style["id"],
                    min_width=min_width,
                    max_width=max_width,
                    min_vertical_length=int(geometry.get("min_vertical_length_px", 4)),
                ),
            )
        elif style["kind"] == "filled":
            bodies = detect_filled_bodies(
                mask,
                bounds,
                FilledConfig(
                    style_id=style["id"],
                    min_width=min_width,
                    max_width=max_width,
                    min_body_height=int(geometry.get("min_body_height_px", 2)),
                ),
            )
            bridge_enabled = bool(geometry.get("bridge_filled_body_fragments", False))
            body_bridge_requested |= bridge_enabled
            if bridge_enabled:
                diagnostic = {
                    "style_id": style["id"],
                    "requested": True,
                    "occluder_role": geometry.get("occluder_role"),
                    "raw_fragment_count": len(bodies),
                }
                minimum_separation = float(
                    geometry.get("min_occluder_color_separation", 1.0)
                )
                color_separable = occluder_colors_are_separable(
                    colors,
                    float(style.get("tolerance", 12)),
                    occluder_colors,
                    float(geometry.get("verified_occluder_tolerance", 12)),
                    minimum_separation,
                )
                diagnostic["color_separable"] = color_separable
                if geometry.get("occluder_role") != "topology_only_not_numeric_fill":
                    diagnostic.update(
                        {"status": "not_applied", "reason_code": "invalid_occluder_role"}
                    )
                elif occluder_mask is None:
                    diagnostic.update(
                        {"status": "not_applied", "reason_code": "verified_occluder_required"}
                    )
                elif not color_separable:
                    diagnostic.update(
                        {
                            "status": "not_applied",
                            "reason_code": "occluder_color_not_separable",
                        }
                    )
                else:
                    bridge_config = FilledBodyBridgeConfig(
                        enabled=True,
                        max_gap=int(geometry.get("max_body_occlusion_gap_px", 8)),
                        max_center_delta=float(
                            geometry.get("max_body_fragment_center_delta_px", 2)
                        ),
                        max_edge_delta=int(
                            geometry.get("max_body_fragment_edge_delta_px", 3)
                        ),
                        max_width_delta=int(
                            geometry.get("max_body_fragment_width_delta_px", 4)
                        ),
                        max_union_width=int(
                            geometry.get("max_body_fragment_union_width_px", max_width)
                        ),
                        min_horizontal_overlap=int(
                            geometry.get("min_body_fragment_horizontal_overlap_px", 1)
                        ),
                        occluder_vertical_radius=int(
                            geometry.get("body_occluder_vertical_radius_px", 0)
                        ),
                        min_occluder_row_coverage=float(
                            geometry.get("min_body_occluder_row_coverage", 1.0)
                        ),
                        min_color_separation=minimum_separation,
                        occluder_role=str(geometry["occluder_role"]),
                    )
                    bodies = merge_occluded_filled_body_fragments(
                        bodies,
                        occluder_mask,
                        bridge_config,
                    )
                    diagnostic.update(
                        {
                            "status": "applied",
                            "reason_code": None,
                            "merged_body_count": len(bodies),
                            "accepted_bridge_count": sum(
                                len(body.occlusion_bridges) for body in bodies
                            ),
                        }
                    )
                body_bridge_diagnostics.append(diagnostic)
        else:
            raise ExtractionRefused("unsupported_body_style")
        for body in bodies:
            wick = measure_wick(
                mask,
                body,
                max_center_offset=int(geometry.get("max_wick_center_offset_px", 2)),
                max_connection_gap=int(geometry.get("max_wick_connection_gap_px", 1)),
                occluder_mask=occluder_mask,
                max_occlusion_gap=int(geometry.get("max_occlusion_gap_px", 0)),
            )
            all_candidates.append(
                CandleCandidate(body=body, wick=wick, direction=style["direction"])
            )
    result = assemble_extraction(
        all_candidates,
        calibration,
        duplicate_distance=float(extraction_config.get("duplicate_distance_px", 15)),
    )
    price_axis_metadata = {
        "scale": "linear",
        "anchors": [list(point) for point in calibration.anchors],
        "slope": calibration.slope,
        "intercept": calibration.intercept,
    }
    if axis.get("require_anchor_evidence") is True:
        price_axis_metadata["anchor_verifications"] = anchor_verifications
        price_axis_metadata["anchors"] = [list(point) for point in declared_anchors]
        price_axis_metadata["declared_anchors"] = [
            list(point) for point in declared_anchors
        ]
        price_axis_metadata["calibrated_anchors"] = [
            list(point) for point in calibration.anchors
        ]
    metadata = {
        "source_contract": asdict(actual),
        "coordinate_space": "original_raster_pixels",
        "plot_bounds": list(bounds),
        "price_axis": price_axis_metadata,
        "styles": extraction_config["styles"],
        "algorithm_version": "candidate-v2" if body_bridge_requested else "candidate-v1",
        "body_occluder_bridging": body_bridge_diagnostics,
    }
    if axis.get("require_anchor_evidence") is True:
        metadata["refusal_reasons"] = []
    return result, metadata


def _require_empty_output_dir(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty evidence directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)


def write_extraction_artifacts(
    image_path: Path | str,
    result: ExtractionResult,
    metadata: dict,
    output_dir: Path | str,
) -> Path:
    output = Path(output_dir)
    _require_empty_output_dir(output)
    csv_fields = [
        "index",
        "x_center",
        "style_id",
        "direction",
        "open",
        "high",
        "low",
        "close",
        "y_body_top",
        "y_body_bottom",
        "y_wick_top",
        "y_wick_bottom",
        "body_left",
        "body_right",
        "confidence",
    ]
    with (output / "data.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        if result.numeric_output_authorized:
            for index, candle in enumerate(result.candles, 1):
                writer.writerow({"index": index, **asdict(candle)})

    algorithm = {
        "name": "raster_kline_candidate",
        "version": metadata.get("algorithm_version", "candidate-v1"),
    }
    run_material = json.dumps(
        {"algorithm": algorithm, "metadata": metadata},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    report = {
        "schema_version": 1,
        "algorithm": algorithm,
        "run_id": hashlib.sha256(run_material).hexdigest()[:16],
        **metadata,
        "numeric_output_authorized": result.numeric_output_authorized,
        "candle_count": len(result.candles),
        "candles": [asdict(candle) for candle in result.candles],
        "coverage_ledger": [asdict(record) for record in result.coverage_ledger],
        "candidates": [asdict(candidate) for candidate in result.candidates],
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    image = Image.open(image_path).convert("RGB")
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    for candidate, ledger in zip(result.candidates, result.coverage_ledger):
        body = candidate.body
        color = (0, 255, 0) if ledger.status == "extracted" else (255, 0, 255)
        draw.rectangle((body.left, body.top, body.right, body.bottom), outline=color, width=2)
        draw.line(
            (round(body.center), candidate.wick.top, round(body.center), candidate.wick.bottom),
            fill=color,
            width=2,
        )
        draw.text((body.left, max(0, body.top - 14)), ledger.status, fill=color)
    overlay.save(output / "overlay.png")
    return output
