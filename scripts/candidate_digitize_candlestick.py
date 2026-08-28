"""FigureSpec adapter for the evidence-bound candlestick candidate extractor."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from PIL import UnidentifiedImageError

try:
    from candlestick_extractor import (
        ExtractionRefused,
        extract_candlesticks,
        write_extraction_artifacts,
    )
    from extractor_registry import ROUTE_BY_ID
    from figure_spec import CANDLESTICK_STYLE_GEOMETRY_FIELDS, figure_spec_readiness
except ImportError:  # pragma: no cover - package-style invocation
    from .candlestick_extractor import (
        ExtractionRefused,
        extract_candlesticks,
        write_extraction_artifacts,
    )
    from .extractor_registry import ROUTE_BY_ID
    from .figure_spec import CANDLESTICK_STYLE_GEOMETRY_FIELDS, figure_spec_readiness


CANDLESTICK_ROUTE_ID = "raster_candlestick_candidate"
PRICE_AXIS_FIELDS = ("scale", "verification", "require_anchor_evidence")
PRICE_ANCHOR_FIELDS = ("pixel", "value")
PRICE_ANCHOR_EVIDENCE_FIELDS = (
    "kind",
    "role",
    "x_range",
    "color",
    "tolerance",
    "min_support_ratio",
    "max_row_offset_px",
)
STYLE_FIELDS = ("id", "kind", "colors", "tolerance", "direction")


def _allowed_fields(value: dict, fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: value[key] for key in fields if key in value}


def _price_axis_config(value: dict) -> dict[str, Any]:
    price_axis = _allowed_fields(value, PRICE_AXIS_FIELDS)
    price_axis["anchors"] = []
    for anchor in value["anchors"]:
        safe_anchor = _allowed_fields(anchor, PRICE_ANCHOR_FIELDS)
        if isinstance(anchor.get("evidence"), dict):
            safe_anchor["evidence"] = _allowed_fields(
                anchor["evidence"],
                PRICE_ANCHOR_EVIDENCE_FIELDS,
            )
        price_axis["anchors"].append(safe_anchor)
    return price_axis


def _style_configs(
    values: list[dict],
    geometry_by_style: dict[str, dict],
) -> list[dict[str, Any]]:
    styles = []
    for value in values:
        style = _allowed_fields(value, STYLE_FIELDS)
        style["geometry"] = _allowed_fields(
            geometry_by_style[value["id"]],
            CANDLESTICK_STYLE_GEOMETRY_FIELDS,
        )
        styles.append(style)
    return styles


def extraction_config_from_spec(spec: dict) -> tuple[Path, dict]:
    """Translate one verified candlestick panel without adding inferred values."""

    panel = spec["panels"][0]
    if panel["route"]["route_id"] != CANDLESTICK_ROUTE_ID:
        raise ValueError("unsupported_extract_route")
    route_config = panel["route_config"]
    for field in ("exclusions", "occluders"):
        if set(route_config[field]) - {"verification", "regions"}:
            raise ExtractionRefused(f"unsupported_{field}_controls")
        if route_config[field]["regions"]:
            raise ExtractionRefused(f"unsupported_{field}_regions")
    geometry_by_style = route_config["geometry"]["styles"]
    return Path(spec["source"]["input_file"]), {
        "source_contract": {
            key: spec["source"][key] for key in ("sha256", "width", "height")
        },
        "plot_bounds": list(panel["plot_bounds"]),
        "price_axis": _price_axis_config(route_config["price_axis"]),
        "styles": _style_configs(route_config["styles"], geometry_by_style),
        "duplicate_distance_px": route_config.get("duplicate_distance_px", 15),
    }


def ensure_empty_output_dir(output_dir: Path | str) -> Path:
    """Create an evidence directory, refusing to mutate one with prior evidence."""

    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            f"refusing to overwrite non-empty evidence directory: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)
    return output


def _source_identity(spec: dict | None) -> dict[str, Any]:
    source = spec.get("source", {}) if isinstance(spec, dict) else {}
    return {
        key: source[key]
        for key in ("input_file", "sha256", "width", "height")
        if key in source
    }


def _selected_route(spec: dict | None) -> str | None:
    if not isinstance(spec, dict):
        return None
    panels = spec.get("panels")
    if not isinstance(panels, list) or not panels or not isinstance(panels[0], dict):
        return None
    route = panels[0].get("route")
    return route.get("route_id") if isinstance(route, dict) else None


def write_refusal_report(
    spec: dict | None,
    output_dir: Path | str,
    *,
    refusal_reasons: list[str],
    readiness: dict[str, Any] | None = None,
    validation_errors: list[str] | None = None,
    detector_details: dict[str, Any] | None = None,
) -> Path:
    """Write the only authorized artifact for a refused extraction."""

    output = ensure_empty_output_dir(output_dir)
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "refused",
        "numeric_output_authorized": False,
        "refusal_reasons": refusal_reasons,
        "source": _source_identity(spec),
        "selected_route": _selected_route(spec),
    }
    if readiness is not None:
        report["readiness"] = readiness
    if validation_errors is not None:
        report["validation_errors"] = validation_errors
    if detector_details:
        report["detector_details"] = detector_details
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def _detector_refusal_details(result: Any, metadata: dict[str, Any]) -> dict[str, Any]:
    details = {
        "candle_count": len(result.candles),
        "candidate_count": len(result.candidates),
        "coverage_ledger": [asdict(record) for record in result.coverage_ledger],
    }
    if metadata.get("algorithm_version") in {"candidate-v1", "candidate-v2"}:
        details["algorithm_version"] = metadata["algorithm_version"]
    if metadata.get("coordinate_space") == "original_raster_pixels":
        details["coordinate_space"] = "original_raster_pixels"
    return details


def _detector_refusal_reasons(result: Any, metadata: dict[str, Any]) -> list[str]:
    reasons = list(metadata.get("refusal_reasons", []))
    reasons.extend(
        record.reason_code
        for record in result.coverage_ledger
        if record.reason_code is not None
    )
    unique_reasons = list(dict.fromkeys(reasons))
    return unique_reasons or ["detector_not_authorized"]


def _candlestick_readiness(spec: dict) -> dict[str, Any]:
    """Combine shared validation with registry-owned candlestick authorization."""

    shared = figure_spec_readiness(spec)
    canonical = list(ROUTE_BY_ID[CANDLESTICK_ROUTE_ID].required_confirmations)
    panels = spec.get("panels", []) if isinstance(spec, dict) else []
    panel = panels[0] if panels and isinstance(panels[0], dict) else {}
    declared = panel.get("required_confirmations", [])
    declared_names = set(declared) if isinstance(declared, list) else set()
    confirmations = panel.get("confirmations", {})
    confirmed = confirmations if isinstance(confirmations, dict) else {}
    missing_required = [name for name in canonical if name not in declared_names]
    missing_canonical = [
        name
        for name in canonical
        if confirmed.get(name) != "verified"
    ]

    readiness_reasons: list[str] = []
    if spec.get("status") != "ready_for_assisted_extraction":
        readiness_reasons.append("spec_status_not_ready")
    if shared["status"] != "ready_for_assisted_extraction":
        readiness_reasons.append("shared_figure_spec_not_ready")
    if missing_required:
        readiness_reasons.append("canonical_required_confirmations_truncated")
    if missing_canonical:
        readiness_reasons.append("canonical_confirmations_not_verified")

    if shared["status"] == "invalid":
        status = "invalid"
    elif readiness_reasons:
        status = "needs_verified_configuration"
    else:
        status = "ready_for_assisted_extraction"
    return {
        **shared,
        "status": status,
        "shared_readiness_status": shared["status"],
        "spec_status": spec.get("status"),
        "canonical_required_confirmations": canonical,
        "missing_required_confirmations": missing_required,
        "missing_canonical_confirmations": missing_canonical,
        "readiness_reasons": readiness_reasons,
    }


def run_candlestick_extraction(spec: dict, output_dir: Path | str) -> bool:
    """Run the registered candidate and return whether numeric output was authorized."""

    ensure_empty_output_dir(output_dir)
    readiness = _candlestick_readiness(spec)
    if readiness["status"] != "ready_for_assisted_extraction":
        write_refusal_report(
            spec,
            output_dir,
            refusal_reasons=["figure_spec_not_ready"],
            readiness=readiness,
        )
        return False

    try:
        image_path, extraction_config = extraction_config_from_spec(spec)
        result, metadata = extract_candlesticks(image_path, extraction_config)
    except FileNotFoundError:
        write_refusal_report(
            spec,
            output_dir,
            refusal_reasons=["source_unavailable"],
            readiness=readiness,
        )
        return False
    except UnidentifiedImageError:
        write_refusal_report(
            spec,
            output_dir,
            refusal_reasons=["source_not_image"],
            readiness=readiness,
        )
        return False
    except OSError:
        write_refusal_report(
            spec,
            output_dir,
            refusal_reasons=["source_unreadable"],
            readiness=readiness,
        )
        return False
    except ExtractionRefused as exc:
        write_refusal_report(
            spec,
            output_dir,
            refusal_reasons=[exc.reason_code],
            readiness=readiness,
        )
        return False

    if not result.numeric_output_authorized:
        write_refusal_report(
            spec,
            output_dir,
            refusal_reasons=_detector_refusal_reasons(result, metadata),
            readiness=readiness,
            detector_details=_detector_refusal_details(result, metadata),
        )
        return False

    authorized_metadata = {
        **metadata,
        "selected_route": CANDLESTICK_ROUTE_ID,
        "figure_spec_readiness": readiness,
    }
    write_extraction_artifacts(
        image_path,
        result,
        authorized_metadata,
        output_dir,
    )
    return True
