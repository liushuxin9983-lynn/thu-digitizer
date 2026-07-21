"""Publish Nature Communications Fig. 1f as a label-first donut case."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import re
from pathlib import Path, PureWindowsPath


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "agents" / "nature-40822-fig1f"
TARGET = ROOT / "gallery" / "assets" / "cases" / "nature-40822-fig1f"
MANIFEST = ROOT / "gallery" / "data" / "basics.json"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.is_file():
            return path
    raise FileNotFoundError("No canonical evidence file found: " + ", ".join(map(str, paths)))


def copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)


def scrub_local_paths(value):
    if isinstance(value, dict):
        return {key: scrub_local_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub_local_paths(item) for item in value]
    if isinstance(value, str) and re.match(r"^[A-Za-z]:[\\/]", value):
        return PureWindowsPath(value).name
    return value


def publish_evidence(source: Path, target: Path) -> None:
    """Copy evidence while removing workstation-specific paths from JSON."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".json":
        payload = scrub_local_paths(json.loads(source.read_text(encoding="utf-8")))
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif source.resolve() != target.resolve():
        copy(source, target)


def build_case() -> dict:
    TARGET.mkdir(parents=True, exist_ok=True)
    evidence = {
        "measurement-source.png": ARTIFACT / "figure1-original.png",
        "original.png": ARTIFACT / "panel-original.png",
        "overlay.png": ARTIFACT / "overlay.png",
        "recreated.png": ARTIFACT / "recreated.png",
        "candidate-data.csv": ARTIFACT / "data.csv",
        "sector-geometry.csv": ARTIFACT / "sector-geometry.csv",
        "candidate-report.json": ARTIFACT / "report.json",
        "preflight-report.json": ARTIFACT / "preflight-report.json",
        "figure-spec.json": ARTIFACT / "figure-spec.json",
        "candidate_digitize_donut_case.py": ARTIFACT / "candidate_digitize_donut_case.py",
        "test_candidate_digitize_donut_case.py": ARTIFACT / "test_candidate_digitize_donut_case.py",
        "README.md": ARTIFACT / "README.md",
        "SOURCES.md": ARTIFACT / "SOURCE_AND_LICENSE.md",
    }
    for name, artifact_path in evidence.items():
        publish_evidence(first_existing(artifact_path, TARGET / name), TARGET / name)

    rows: list[dict] = []
    with (TARGET / "candidate-data.csv").open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            rows.append({
                "kind": "point",
                "shape": "circle",
                "series": raw["cell_type"],
                "category": raw["chart_group"],
                "value": raw["displayed_value_percent"],
                "unit": "percent",
                "label_sum": raw["group_label_sum_percent"],
                "numeric_use_allowed": "true",
                "value_status": "visible_printed_label",
                "pixel_x": round(float(raw["label_anchor_x_original_px"]) - 1000, 3),
                "pixel_y": round(float(raw["label_anchor_y_original_px"]) - 420, 3),
                "radius": 12,
                "fill": raw["color_hex"],
            })
    fields = list(rows[0])
    with (TARGET / "data.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    candidate = json.loads((TARGET / "candidate-report.json").read_text(encoding="utf-8"))
    report = {
        "schema_version": 1,
        "case_id": "nature-40822-fig1f",
        "status": "partial_visible",
        "route": candidate["algorithm"],
        "shared_pie_route": candidate["preflight"]["route_id"],
        "expected_detection_count_passed": False,
        "source_data_role": "independent_validation_only",
        "normalization_applied_to_primary_values": False,
        "measurement": {
            "file": "measurement-source.png",
            "sha256": digest(TARGET / "measurement-source.png"),
            "size": [2050, 1399],
            "gallery_crop": candidate["panel"]["bounds_original_px"],
            "resampling_applied": False,
        },
        "visible_label_extraction": candidate["visible_label_extraction"],
        "sector_geometry_validation": {
            "role": "validation_only_case_local_candidate",
            "mean_absolute_percentage_point_error": candidate["sector_geometry_validation"]["mean_absolute_percentage_point_error"],
            "maximum_absolute_percentage_point_error": candidate["sector_geometry_validation"]["maximum_absolute_percentage_point_error"],
        },
        "validation": {"status": "not_comparable", "filled_from_external_data": 0},
        "limitations": [
            "Numeric use is authorized only for the 18 explicitly printed labels.",
            "The four printed label sums are retained as 97.5, 90.6, 70.3, and 73.6 rather than forced to 100.",
            "Sector geometry remains a case-local validation candidate; the shared pie/donut route is not implemented.",
        ],
    }
    (TARGET / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "id": "pie",
        "title": "环形饼图 / Donut",
        "subtitle": "四组可见百分比标签",
        "status": "partial_visible",
        "statusLabel": "部分可见提取 · 18 标签",
        "description": "从 Nature Communications Fig. 1f 提取四个 donut 上明确印出的 18 个百分比；原标签和不强制补到 100，扇区角度仅作案例级验证。",
        "metrics": [{"label": "可见标签", "value": "18 / 18"}, {"label": "几何验证 MAE", "value": "0.596 pp"}],
        "journal": "Nature Communications",
        "figure": "Fig. 1f",
        "articleTitle": "Driver gene combinations dictate cutaneous squamous cell carcinoma disease continuum progression",
        "articleUrl": "https://www.nature.com/articles/s41467-023-40822-9",
        "figureUrl": "https://www.nature.com/articles/s41467-023-40822-9/figures/1",
        "styleSpec": {
            "renderer": "paper-native-geometry",
            "fidelity": "visible_geometry_candidate",
            "label": "论文原生画布 · 可见标签提取",
            "note": "交互命中层对应 18 个印刷标签；显示值保持原样，环形角度按组内可见值重建但不替代原值。",
            "canvas": {"width": 1025, "height": 215},
            "rasterEvidenceInteractive": True,
        },
        "assets": {
            "original": "assets/cases/nature-40822-fig1f/original.png",
            "overlay": "assets/cases/nature-40822-fig1f/overlay.png",
            "recreated": "assets/cases/nature-40822-fig1f/recreated.png",
            "data": "assets/cases/nature-40822-fig1f/data.csv",
            "report": "assets/cases/nature-40822-fig1f/report.json",
        },
    }


def publish_manifest(sample: dict) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    existing = next((index for index, item in enumerate(manifest["samples"]) if item["id"] == "pie"), None)
    if existing is not None:
        manifest["samples"][existing] = sample
    else:
        anchor = next(index for index, item in enumerate(manifest["samples"]) if item["id"] == "bar-percent-stacked")
        manifest["samples"].insert(anchor + 1, sample)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    publish_manifest(build_case())
    print("published requested Nature donut gallery case")


if __name__ == "__main__":
    main()
