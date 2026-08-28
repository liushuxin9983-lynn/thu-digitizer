"""FigureSpec adapter for the evidence-bound candlestick candidate extractor."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

try:
    from candlestick_extractor import (
        ExtractionRefused,
        extract_candlesticks,
        write_extraction_artifacts,
    )
    from figure_spec import figure_spec_readiness
except ImportError:  # pragma: no cover - package-style invocation
    from .candlestick_extractor import (
        ExtractionRefused,
        extract_candlesticks,
        write_extraction_artifacts,
    )
    from .figure_spec import figure_spec_readiness


CANDLESTICK_ROUTE_ID = "raster_candlestick_candidate"


def extraction_config_from_spec(spec: dict) -> tuple[Path, dict]:
    """Translate one verified candlestick panel without adding inferred values."""

    panel = spec["panels"][0]
    if panel["route"]["route_id"] != CANDLESTICK_ROUTE_ID:
        raise ValueError("unsupported_extract_route")
    route_config = panel["route_config"]
    return Path(spec["source"]["input_file"]), {
        "source_contract": {
            key: spec["source"][key] for key in ("sha256", "width", "height")
        },
        "plot_bounds": panel["plot_bounds"],
        "price_axis": route_config["price_axis"],
        "styles": route_config["styles"],
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
    return {
        **metadata,
        "candle_count": len(result.candles),
        "candles": [asdict(candle) for candle in result.candles],
        "coverage_ledger": [asdict(record) for record in result.coverage_ledger],
        "candidates": [asdict(candidate) for candidate in result.candidates],
    }


def _detector_refusal_reasons(result: Any, metadata: dict[str, Any]) -> list[str]:
    reasons = list(metadata.get("refusal_reasons", []))
    reasons.extend(
        record.reason_code
        for record in result.coverage_ledger
        if record.reason_code is not None
    )
    unique_reasons = list(dict.fromkeys(reasons))
    return unique_reasons or ["detector_not_authorized"]


def run_candlestick_extraction(spec: dict, output_dir: Path | str) -> bool:
    """Run the registered candidate and return whether numeric output was authorized."""

    ensure_empty_output_dir(output_dir)
    readiness = figure_spec_readiness(spec)
    if readiness["status"] != "ready_for_assisted_extraction":
        write_refusal_report(
            spec,
            output_dir,
            refusal_reasons=["figure_spec_not_ready"],
            readiness=readiness,
        )
        return False

    image_path, extraction_config = extraction_config_from_spec(spec)
    try:
        result, metadata = extract_candlesticks(image_path, extraction_config)
    except ExtractionRefused as exc:
        write_refusal_report(
            spec,
            output_dir,
            refusal_reasons=[exc.reason_code],
            readiness=readiness,
            detector_details=exc.details,
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
