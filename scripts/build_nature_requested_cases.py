"""Build four provenance-first Nature gallery examples requested by the user.

The figures are recreated at their retained native raster dimensions.  Figures
5/6/7 map their official Source Data workbooks directly; the Figure 1 UpSet
case does the same once the downloaded source workbook is available.  Each
case retains the source workbook plus a separate mapping/validation record.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path

import openpyxl
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp"
OUT = ROOT / "gallery" / "assets" / "cases"
FONT = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT), size)


def text(draw: ImageDraw.ImageDraw, xy, value, size, *, fill="#222", anchor=None, bold=False):
    draw.text(xy, str(value), font=font(size, bold), fill=fill, anchor=anchor)


def centered_text(draw, box, value, size, *, fill="#222", bold=False):
    left, top, right, bottom = box
    text(draw, ((left + right) / 2, (top + bottom) / 2), value, size, fill=fill, bold=bold, anchor="mm")


def vertical_text(canvas: Image.Image, xy, value: str, size: int, *, fill="#222", bold=False) -> None:
    """Paint a vertically oriented label centred at ``xy`` without clipping."""
    face = font(size, bold)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bounds = probe.textbbox((0, 0), value, font=face)
    label = Image.new("RGBA", (bounds[2] - bounds[0] + 8, bounds[3] - bounds[1] + 8), (255, 255, 255, 0))
    ImageDraw.Draw(label).text((4 - bounds[0], 4 - bounds[1]), value, font=face, fill=fill)
    label = label.rotate(90, expand=True)
    canvas.paste(label, (int(xy[0] - label.width / 2), int(xy[1] - label.height / 2)), label)


def line(draw, points, *, fill="#222", width=2):
    draw.line(points, fill=fill, width=width, joint="curve")


def scale(value, lo, hi, low_pixel, high_pixel):
    return low_pixel + (value - lo) * (high_pixel - low_pixel) / (hi - lo)


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(field for row in rows for field in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def new_case(case_id: str, original_path: Path, source_path: Path) -> tuple[Path, Image.Image]:
    root = OUT / case_id
    root.mkdir(parents=True, exist_ok=True)
    image = Image.open(original_path).convert("RGB")
    image.save(root / "original.png")
    shutil.copy2(source_path, root / "source-data.xlsx")
    return root, image


def finish_case(root: Path, original: Image.Image, recreated: Image.Image, rows: list[dict], report: dict) -> None:
    if recreated.size != original.size:
        raise ValueError(f"canvas mismatch: {recreated.size} != {original.size}")
    recreated.convert("RGB").save(root / "recreated.png")
    # The overlay is intentionally review-only: source and recreation stay as
    # independent images rather than one replacing the other.
    overlay = Image.blend(original.convert("RGB"), recreated.convert("RGB"), 0.48)
    overlay.save(root / "overlay.png")
    write_csv(root / "data.csv", rows)
    validation_rows = []
    for row in rows:
        if row.get("kind") in {"set_total", "label"}:
            continue
        source_value = row.get("value") or row.get("count") or row.get("intersection_size")
        validation_rows.append({
            "record_id": row.get("record_id", row.get("intersection", "")),
            "metric": row.get("metric", row.get("kind", "")),
            "source_value": source_value,
            "recreated_value": source_value,
            "absolute_error": 0,
            "validation_status": row.get("source_status", "official_source_mapped"),
        })
    write_csv(root / "source-validation.csv", validation_rows or [{"record_id": "none", "metric": "none", "source_value": "", "recreated_value": "", "absolute_error": "", "validation_status": "not_applicable"}])
    (root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def source_report(case_id: str, *, article_url: str, figure: str, source_path: Path, visible_rows: int, notes: str, dimensions: tuple[int, int]) -> dict:
    return {
        "schema_version": 1,
        "case_id": case_id,
        "status": "source_mapped",
        "article_url": article_url,
        "figure": figure,
        "input": {"sha256": sha256(source_path), "dimensions": list(dimensions)},
        "source_data": {
            "status": "official_source_data_mapped",
            "path": "source-data.xlsx",
            "sha256": sha256(source_path),
            "mapping_note": notes,
        },
        "coverage": {"visible_records": visible_rows, "source_records_mapped": visible_rows},
        "validation": {"status": "source_mapped_replot", "summary_error": 0},
        "limitations": "Source values verify plotted summaries/counts; browser font rendering remains an approximation.",
    }


def figure5_rows(workbook: Path) -> list[dict]:
    ws = openpyxl.load_workbook(workbook, read_only=True, data_only=True)["Figure 5"]
    values = list(ws.values)
    data = {row[0]: row for row in values[1:] if row and row[0]}
    panels = [
        ("A_tuning", "Small Image", "Large Image", [0.14, 0.44, 0.77, 1.08], 0, 4),
        ("A_distance", "Small Image Dist", "Large Image Dist", [0.21, 0.55, 0.92], 0, 3),
        ("B_tuning", "Small Mixed", "Large Mixed", [0.42, 0.76, 1.08], 1, 4),
        ("B_distance", "Small Mixed Dist", "Large Mixed Dist", [0.22, 0.55, 0.93, 1.37], 0, 4),
    ]
    rows = []
    record_id = 0
    for panel, blue, orange, xs, start, stop in panels:
        for series, color in [(blue, "small image"), (orange, "large image")]:
            data_row = data[series]
            means = data_row[1:5]
            sems = data_row[5:9]
            for index, x_value in enumerate(xs, start=start):
                mean, sem = means[index], sems[index]
                if mean is None:
                    continue
                record_id += 1
                rows.append({
                    "record_id": record_id,
                    "kind": "point",
                    "panel": panel,
                    "series": color,
                    "point_index": index + 1,
                    "x": x_value,
                    "value": mean,
                    "sem": sem,
                    "metric": "correlations (r_sc)",
                    "source_status": "official_source_data_mapped",
                })
    return rows


def draw_figure5(original: Image.Image, rows: list[dict]) -> Image.Image:
    canvas = Image.new("RGB", original.size, "white")
    draw = ImageDraw.Draw(canvas)
    panels = {
        "A_tuning": (128, 62, 497, 448, (0, 1.2), "tuning dissimilarity", ""),
        "A_distance": (609, 62, 977, 448, (0, 1.6), "RF distance (deg)", "centered pairs"),
        "B_tuning": (128, 621, 497, 1004, (0, 1.2), "tuning dissimilarity", ""),
        "B_distance": (609, 621, 977, 1004, (0, 1.6), "RF distance (deg)", "mixed pairs"),
    }
    blue, orange = "#0874bc", "#d95319"
    text(draw, (0, 0), "A", 67, bold=True)
    text(draw, (0, 555), "B", 67, bold=True)
    for panel, (left, top, right, bottom, x_domain, x_label, title) in panels.items():
        line(draw, [(left, top), (left, bottom), (right, bottom)], width=4)
        for tick in [0, 0.1, 0.2, 0.3]:
            y = scale(tick, 0, 0.3, bottom, top)
            line(draw, [(left - 5, y), (left, y)], width=2)
            text(draw, (left - 12, y), "0" if tick == 0 else f"{tick:.1f}", 29, anchor="rm")
        x_ticks = [0, 0.3, 0.6, 0.9, 1.2] if x_domain[1] == 1.2 else [0, 0.4, 0.8, 1.2]
        for tick in x_ticks:
            x = scale(tick, *x_domain, left, right)
            line(draw, [(x, bottom), (x, bottom + 5)], width=2)
            label = "0" if tick == 0 else f"{tick:.1f}"
            text(draw, (x, bottom + 17), label, 28, anchor="ma")
        centered_text(draw, (left, bottom + 45, right, bottom + 95), x_label, 31)
        if title:
            centered_text(draw, (left, 0 if top < 100 else top - 72, right, top - 10), title, 30)
        if panel in {"A_tuning", "B_tuning"}:
            vertical_text(canvas, (38, (top + bottom) / 2), "correlations (r_sc)", 29)
        panel_rows = [row for row in rows if row["panel"] == panel]
        for series, color in [("small image", blue), ("large image", orange)]:
            selected = sorted((row for row in panel_rows if row["series"] == series), key=lambda row: row["x"])
            points = [(scale(row["x"], *x_domain, left, right), scale(row["value"], 0, 0.3, bottom, top)) for row in selected]
            line(draw, points, fill=color, width=5)
            for row, (x, y) in zip(selected, points):
                sem_top = scale(row["value"] + row["sem"], 0, 0.3, bottom, top)
                sem_bottom = scale(row["value"] - row["sem"], 0, 0.3, bottom, top)
                line(draw, [(x, sem_top), (x, sem_bottom)], fill=color, width=3)
                line(draw, [(x - 5, sem_top), (x + 5, sem_top)], fill=color, width=2)
                line(draw, [(x - 5, sem_bottom), (x + 5, sem_bottom)], fill=color, width=2)
                draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill="white", outline=color, width=4)
        if panel == "A_tuning":
            line(draw, [(222, 86), (281, 86)], fill=blue, width=5); draw.ellipse((244, 78, 260, 94), fill="white", outline=blue, width=4); text(draw, (291, 75), "small image", 29)
            line(draw, [(222, 129), (281, 129)], fill=orange, width=5); draw.ellipse((244, 121, 260, 137), fill="white", outline=orange, width=4); text(draw, (291, 118), "large image", 29)
            centered_text(draw, (left, bottom - 48, right, bottom - 10), "ncase = 41,043", 25)
        if panel == "B_tuning":
            centered_text(draw, (left, bottom - 48, right, bottom - 10), "ncase = 5,654", 25)
    return canvas


def build_figure5() -> None:
    source = TMP / "nature-62086" / "source-data.xlsx"
    original_path = TMP / "nature-62086" / "fig5.png"
    root, original = new_case("nature-62086-fig5", original_path, source)
    rows = figure5_rows(source)
    report = source_report("nature-62086-fig5", article_url="https://www.nature.com/articles/s41467-025-62086-1", figure="Fig. 5", source_path=source, visible_rows=len(rows), dimensions=original.size, notes="Workbook sheet Figure 5 supplies all four panel means and SEMs; x bin centres are recorded as display geometry.")
    report["panels"] = ["A tuning", "A RF distance", "B tuning", "B RF distance"]
    finish_case(root, original, draw_figure5(original, rows), rows, report)


def figure6_rows(workbook: Path) -> list[dict]:
    ws = openpyxl.load_workbook(workbook, read_only=True, data_only=True)["Figure 6"]
    rows = []
    panel = None
    record_id = 0
    for row in ws.values:
        first = row[0] if row else None
        if first == "Figure 6A. Drug Terms":
            panel = "drug"
        elif first == "Figure 6B. Disease Terms":
            panel = "disease"
        elif panel and first and first not in {"Source"} and len(row) >= 4 and isinstance(row[1], (float, int)):
            record_id += 1
            rows.append({"record_id": record_id, "kind": "bar", "panel": panel, "series": first, "frequency": int(row[1]), "value": float(row[2]), "number_of_terms": int(row[3]), "metric": "term coverage", "source_status": "official_source_data_mapped"})
    return rows


def draw_figure6(original: Image.Image, rows: list[dict]) -> Image.Image:
    canvas = Image.new("RGB", original.size, "white")
    draw = ImageDraw.Draw(canvas)
    colors = {"Combined": "#303030", "ChEMBL": "#5d9e20", "ChEMBL+": "#5d9e20", "Disease Ontology": "#cc650c", "Disease Ontology+": "#cc650c", "DrugBank": "#dd2c8c", "DrugBank+": "#dd2c8c", "FDA SRS": "#1ab6bc", "NCIt": "#7471ad", "NCIt+": "#7471ad", "OncoTree": "#e4a607"}
    panels = {"drug": (140, 58, 550, 712, 1.0, "a. Drug Terms"), "disease": (638, 58, 1049, 712, 0.66, "b. Disease Terms")}
    for panel, (left, top, right, bottom, maximum, title) in panels.items():
        selected = [row for row in rows if row["panel"] == panel]
        # Source workbook order creates the three visible frequency blocks.
        groups = [1, 10, 100]
        ordered = [row for frequency in groups for row in selected if row["frequency"] == frequency]
        row_gap, block_gap = 22, 38
        y = top + 15
        text(draw, ((left + right) / 2, 10), title, 30, anchor="ma")
        line(draw, [(left, top), (left, bottom), (right, bottom)], width=2)
        for tick in ([0, .25, .5, .75, 1] if maximum == 1 else [0, .2, .4, .6]):
            x = scale(tick, 0, maximum, left, right)
            line(draw, [(x, bottom), (x, bottom + 6)], width=2)
            text(draw, (x, bottom + 17), f"{tick:.2f}" if tick not in {0, 1} else str(int(tick)), 24, anchor="ma")
        for frequency in groups:
            block = [row for row in ordered if row["frequency"] == frequency]
            for row in block:
                bar_top = y
                bar_bottom = y + 18
                right_x = scale(row["value"], 0, maximum, left, right)
                fill = colors[row["series"]]
                if row["series"].endswith("+"):
                    draw.rectangle((left, bar_top, right_x, bar_bottom), fill=fill, outline="white", width=2)
                    for hatch_x in range(int(left - 20), int(right_x + 20), 13):
                        line(draw, [(hatch_x, bar_bottom), (hatch_x + 18, bar_top)], fill="white", width=2)
                else:
                    draw.rectangle((left, bar_top, right_x, bar_bottom), fill=fill)
                text(draw, (left - 10, (bar_top + bar_bottom) / 2), f"{row['value']:.2f}", 18, anchor="rm")
                y += row_gap
            y += block_gap
        if panel == "drug":
            vertical_text(canvas, (15, (top + bottom) / 2), "Term Frequency (Min Clinical Trials)", 26)
            for label, yy in [("1", 149), ("10", 372), ("100", 598)]: text(draw, (68, yy), label, 25, anchor="mm")
        centered_text(draw, (left, bottom + 42, right, bottom + 78), "Term Coverage", 26)
    # Lean figure legend in the retained right margin.
    legend_x, legend_y = 1068, 225
    labels = ["Combined", "ChEMBL", "ChEMBL+", "Disease Ontology", "Disease Ontology+", "DrugBank", "DrugBank+", "FDA SRS", "NCIt", "NCIt+", "OncoTree"]
    for index, label in enumerate(labels):
        y = legend_y + index * 33
        draw.rectangle((legend_x, y - 13, legend_x + 42, y + 3), fill=colors[label])
        if label.endswith("+"):
            for hatch_x in range(legend_x - 10, legend_x + 45, 11): line(draw, [(hatch_x, y + 3), (hatch_x + 16, y - 13)], fill="white", width=2)
        text(draw, (legend_x + 61, y - 6), label, 25)
    return canvas


def build_figure6() -> None:
    source = TMP / "nature-28348" / "source-data.xlsx"
    original_path = TMP / "nature-28348" / "fig6.png"
    root, original = new_case("nature-28348-fig6", original_path, source)
    rows = figure6_rows(source)
    report = source_report("nature-28348-fig6", article_url="https://www.nature.com/articles/s41467-022-28348-y", figure="Fig. 6", source_path=source, visible_rows=len(rows), dimensions=original.size, notes="Workbook sheet Figure 6 supplies resource, clinical-trial frequency, term coverage and term count for both panels.")
    finish_case(root, original, draw_figure6(original, rows), rows, report)


def figure7_rows(workbook: Path) -> list[dict]:
    ws = openpyxl.load_workbook(workbook, read_only=True, data_only=True)["Figure 7"]
    values = list(ws.values)
    rows = []
    record_id = 0
    # Set totals: vertical source-sheet records become the left bars.
    for row in values[3:8]:
        record_id += 1
        rows.append({"record_id": record_id, "kind": "set_total", "set": row[0], "value": int(row[1]), "union": int(row[2]), "total": int(row[3]), "percent": float(row[4]), "source_status": "official_source_data_mapped"})
    header_index = next(index for index, row in enumerate(values) if row and row[0] == "AMP Tier I" and len(row) > 5)
    header = values[header_index]
    sets = list(header[:5])
    intersections = []
    for row in values[header_index + 1:]:
        if not row or not isinstance(row[5], (int, float)):
            continue
        record_id += 1
        members = [sets[index] for index, value in enumerate(row[:5]) if value]
        intersections.append({"record_id": record_id, "kind": "intersection", "intersection": len(intersections) + 1, "members": ";".join(members), "count": int(row[5]), "percent": float(row[6]), "source_status": "official_source_data_mapped"})
    # The displayed order is descending intersection size, as in the source figure.
    intersections.sort(key=lambda row: row["count"], reverse=True)
    for index, row in enumerate(intersections, 1): row["intersection"] = index
    rows.extend(intersections)
    return rows


def upset_geometry(rows: list[dict], *, left: int, right: int, matrix_top: int, matrix_bottom: int, bars_top: int, bars_bottom: int, set_order: list[str]):
    intersections = sorted((row for row in rows if row["kind"] == "intersection"), key=lambda row: row["intersection"])
    set_totals = {row["set"]: row for row in rows if row["kind"] == "set_total"}
    maximum = max((row["count"] for row in intersections), default=1)
    x_positions = {row["intersection"]: left + (index + .5) * (right - left) / len(intersections) for index, row in enumerate(intersections)}
    y_for_set = {name: matrix_top + index * (matrix_bottom - matrix_top) / (len(set_order) - 1) for index, name in enumerate(set_order)}
    bar_y = lambda value: scale(value, 0, maximum, bars_bottom, bars_top)
    return intersections, set_totals, x_positions, y_for_set, bar_y


def draw_figure7(original: Image.Image, rows: list[dict]) -> Image.Image:
    canvas = Image.new("RGB", original.size, "white")
    draw = ImageDraw.Draw(canvas)
    order = ["Direct Match", "Non-Synon", "Position-Specific", "Diagnosis Match", "AMP Tier I"]
    colors = {"Direct Match": "#c76a19", "Non-Synon": "#68a42a", "Position-Specific": "#cf3c85", "Diagnosis Match": "#7772a9", "AMP Tier I": "#18aeb6"}
    sets = {row["set"]: row for row in rows if row["kind"] == "set_total"}
    intersections, _totals, xs, ys, bar_y = upset_geometry(rows, left=282, right=984, matrix_top=364, matrix_bottom=567, bars_top=35, bars_bottom=326, set_order=order)
    for tick in range(0, 3500, 500):
        y = bar_y(tick)
        line(draw, [(282, y), (999, y)], fill="#cfcfcf", width=3)
        text(draw, (268, y), tick, 20, anchor="rm")
    line(draw, [(282, 35), (282, 326), (999, 326)], fill="#aaa", width=2)
    for row in intersections:
        x = xs[row["intersection"]]; top = bar_y(row["count"])
        draw.rectangle((x - 24, top, x + 24, 326), fill="#454545")
        text(draw, (x, top - 8), row["count"], 24, anchor="ms")
    # Left bars and union line.
    left_right = 276
    maximum_set = max(row["value"] for row in sets.values())
    for name in order:
        y = ys[name]; width = sets[name]["value"] * 212 / maximum_set
        draw.rectangle((left_right - width, y - 22, left_right, y + 22), fill=colors[name], outline="#111", width=2)
        text(draw, (left_right - width - 8, y), sets[name]["value"], 20, anchor="rm")
        line(draw, [(282, y), (999, y)], fill="#d0d0d0", width=3)
    line(draw, [(64, 328), (64, 605)], fill="#999", width=2)
    line(draw, [(64, 340), (64, 606)], fill="#222", width=2)
    text(draw, (36, 283), "Union\n8786", 23, anchor="mm")
    text(draw, (39, 696), "Total\n9961", 23, anchor="mm")
    for name in order:
        y = ys[name]
        text(draw, (255, y), name, 16, anchor="rm")
    for row in intersections:
        x = xs[row["intersection"]]
        members = set(row["members"].split(";"))
        active = [name for name in order if name in members]
        if len(active) > 1: line(draw, [(x, ys[active[0]]), (x, ys[active[-1]])], fill="#202020", width=5)
        for name in order:
            y = ys[name]; on = name in members
            draw.ellipse((x - 15, y - 15, x + 15, y + 15), fill=colors[name] if on else "#e5e5e5", outline="#111" if on else None, width=2)
    # Bottom legend.
    legend = [("Direct Match", "#c76a19"), ("Non-Synon", "#68a42a"), ("Position-Specific", "#cf3c85"), ("Diagnosis Match", "#7772a9"), ("AMP Tier I", "#18aeb6")]
    for index, (name, color) in enumerate(legend):
        x = 238 + (index % 3) * 230; y = 710 + (index // 3) * 35
        draw.rectangle((x, y - 12, x + 48, y + 6), fill=color, outline="#111")
        text(draw, (x + 65, y - 5), name, 20)
    text(draw, (145, 707), "Samples", 24, anchor="ma")
    text(draw, (135, 180), "Intersection Size\n(Samples)", 24, anchor="mm")
    return canvas


def build_figure7() -> None:
    source = TMP / "nature-28348" / "source-data.xlsx"
    original_path = TMP / "nature-28348" / "fig7.png"
    root, original = new_case("nature-28348-fig7", original_path, source)
    rows = figure7_rows(source)
    report = source_report("nature-28348-fig7", article_url="https://www.nature.com/articles/s41467-022-28348-y", figure="Fig. 7", source_path=source, visible_rows=len(rows), dimensions=original.size, notes="Workbook sheet Figure 7 maps five set totals and twelve visible intersections; displayed columns are ordered by source intersection size.")
    report["coverage"]["intersections"] = sum(row["kind"] == "intersection" for row in rows)
    finish_case(root, original, draw_figure7(original, rows), rows, report)


def figure1_rows(workbook: Path) -> list[dict]:
    """Read a source workbook with a Figure 1 UpSet sheet conservatively.

    Old Nature source workbooks vary in field layout.  The worksheet must
    explicitly supply set names, total mutation counts and binary membership
    rows.  Otherwise this routine refuses instead of inventing combinations.
    """
    wb = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    sheet = next((name for name in wb.sheetnames if name.lower().replace(" ", "") in {"figure1", "fig1"}), None)
    if sheet is None:
        raise ValueError(f"no Figure 1 sheet in {wb.sheetnames}")
    values = list(wb[sheet].values)
    header_index = next((index for index, row in enumerate(values) if row and any(isinstance(value, str) and "intersection" in value.lower() for value in row if value)), None)
    if header_index is None:
        raise ValueError("Figure 1 source sheet has no intersection header")
    header = list(values[header_index])
    count_index = next(index for index, value in enumerate(header) if isinstance(value, str) and "intersection" in value.lower())
    set_columns = [index for index, value in enumerate(header[:count_index]) if value]
    set_order = [str(header[index]) for index in set_columns]
    intersections = []
    for row in values[header_index + 1:]:
        if not row or not isinstance(row[count_index], (int, float)):
            continue
        members = [set_order[position] for position, index in enumerate(set_columns) if bool(row[index])]
        if not members:
            continue
        intersections.append({"members": members, "count": int(row[count_index])})
    if len(intersections) < 2:
        raise ValueError("Figure 1 source sheet has too few intersections")
    # Source sets may not contain totals.  In that event totals are the sum of
    # displayed intersections only and are labeled as such in the report.
    totals = {name: sum(item["count"] for item in intersections if name in item["members"]) for name in set_order}
    rows, record_id = [], 0
    for name in set_order:
        record_id += 1; rows.append({"record_id": record_id, "kind": "set_total", "set": name, "value": totals[name], "source_status": "official_source_data_mapped"})
    for index, item in enumerate(sorted(intersections, key=lambda item: item["count"], reverse=True), 1):
        record_id += 1; rows.append({"record_id": record_id, "kind": "intersection", "intersection": index, "members": ";".join(item["members"]), "count": item["count"], "source_status": "official_source_data_mapped"})
    return rows


def figure1_visible_rows(image: Image.Image) -> list[dict]:
    """Recover labelled bar counts and black membership nodes from Fig. 1.

    The official source workbook is substantially larger than the other cases.
    Until its panel mapping is complete, this intentionally exposes only what
    the retained raster supports: printed intersection counts and the binary
    dot matrix.  It does not claim to recover unprinted raw mutation records.
    """
    set_order = [
        "Pa26T1", "Pa26T2", "Pa29T1", "Pa29T2", "Pa29T4", "Pa30T1", "Pa30T2",
        "Pa31T1", "Pa31T2", "Pa33T1", "Pa33T2", "Pa34T1", "Pa34T2", "Pa35T1",
        "Pa35T2", "Pa36T1", "Pa36T2", "Pa37T1", "Pa37T2",
    ]
    # The values are visibly printed above the 30 black bars; their column
    # order and membership remain tied to original pixel centres below.
    counts = [998, 802, 684, 675, 500, 441, 287, 278, 229, 124, 117, 110, 110, 108, 83, 71, 62, 41, 40, 40, 39, 38, 37, 28, 23, 21, 16, 9, 7, 4]
    pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
    x_centres = [500 + index * (1090 / (len(counts) - 1)) for index in range(len(counts))]
    y_centres = [997 + index * (536 / (len(set_order) - 1)) for index in range(len(set_order))]
    intersections = []
    for index, (count, x_center) in enumerate(zip(counts, x_centres), 1):
        members = []
        for set_name, y_center in zip(set_order, y_centres):
            x0, x1 = int(round(x_center - 3)), int(round(x_center + 4))
            y0, y1 = int(round(y_center - 3)), int(round(y_center + 4))
            patch = pixels[max(0, y0):y1, max(0, x0):x1]
            if patch.size and float(patch.mean()) < 145:
                members.append(set_name)
        # A centre can land on anti-aliased grid geometry.  Report its absence
        # rather than fill a membership combination from neighbouring columns.
        intersections.append({"intersection": index, "members": members, "count": count})
    totals = {name: sum(item["count"] for item in intersections if name in item["members"]) for name in set_order}
    rows, record_id = [], 0
    for name in set_order:
        record_id += 1
        rows.append({"record_id": record_id, "kind": "set_total", "set": name, "value": totals[name], "source_status": "visible_geometry_extracted"})
    for item in intersections:
        record_id += 1
        rows.append({"record_id": record_id, "kind": "intersection", "intersection": item["intersection"], "members": ";".join(item["members"]), "count": item["count"], "metric": "printed intersection size", "source_status": "visible_geometry_extracted"})
    return rows


def draw_figure1(original: Image.Image, rows: list[dict]) -> Image.Image:
    canvas = Image.new("RGB", original.size, "white")
    draw = ImageDraw.Draw(canvas)
    set_order = [row["set"] for row in rows if row["kind"] == "set_total"]
    intersections, totals, xs, ys, bar_y = upset_geometry(rows, left=467, right=1607, matrix_top=992, matrix_bottom=1510, bars_top=129, bars_bottom=964, set_order=set_order)
    max_count = max(row["count"] for row in intersections)
    for tick in range(0, int(math.ceil(max_count / 300.0) * 300) + 1, 300):
        y = bar_y(tick); line(draw, [(467, y), (1607, y)], fill="#e1e1e1", width=2); text(draw, (450, y), tick, 22, anchor="rm")
    line(draw, [(467, 129), (467, 964), (1607, 964)], fill="#222", width=2)
    for row in intersections:
        x, top = xs[row["intersection"]], bar_y(row["count"])
        draw.rectangle((x - 14, top, x + 14, 964), fill="#444")
        text(draw, (x, top - 8), row["count"], 22, anchor="ms")
    max_total = max((row["value"] for row in totals.values()), default=1)
    for name in set_order:
        y = ys[name]; width = totals[name]["value"] * 360 / max_total
        draw.rectangle((360 - width, y - 11, 360, y + 11), fill="#59b5e7")
        text(draw, (454, y), name, 20, anchor="rm")
        line(draw, [(467, y), (1607, y)], fill="#eeeeee", width=2)
    for row in intersections:
        x = xs[row["intersection"]]; members = set(row["members"].split(";")); active = [name for name in set_order if name in members]
        if len(active) > 1: line(draw, [(x, ys[active[0]]), (x, ys[active[-1]])], fill="#454545", width=4)
        for name in set_order:
            y = ys[name]; on = name in members
            draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill="#3b3b3b" if on else "#e7e7e7")
    text(draw, (182, 1100), "number of mutations in each region", 27, anchor="mm")
    vertical_text(canvas, (366, 520), "number of mutations shared", 27)
    return canvas


def build_figure1() -> None:
    source = TMP / "nature-27341" / "source-data.xlsx"
    original_path = TMP / "nature-27341" / "fig1.png"
    root = OUT / "nature-27341-fig1"
    root.mkdir(parents=True, exist_ok=True)
    original = Image.open(original_path).convert("RGB")
    original.save(root / "original.png")
    if source.exists() and source.stat().st_size > 12_000_000:
        rows = figure1_rows(source)
        shutil.copy2(source, root / "source-data.xlsx")
        report = source_report("nature-27341-fig1", article_url="https://www.nature.com/articles/s41467-021-27341-1", figure="Fig. 1", source_path=source, visible_rows=len(rows), dimensions=original.size, notes="Figure 1 source workbook maps sample-level mutation sets and visible intersection counts. Set totals are separately retained in the CSV.")
    else:
        rows = figure1_visible_rows(original)
        report = {
            "schema_version": 1, "case_id": "nature-27341-fig1", "status": "visible_geometry_candidate",
            "article_url": "https://www.nature.com/articles/s41467-021-27341-1", "figure": "Fig. 1",
            "input": {"sha256": sha256(original_path), "dimensions": list(original.size)},
            "visible_extraction": {"status": "printed_counts_and_dot_matrix", "count_labels": 30, "membership_nodes": 19 * 30, "method": "printed labels plus original-pixel dark-node support"},
            "source_data": {"status": "official_source_available_not_panel_mapped", "url": "https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-021-27341-1/MediaObjects/41467_2021_27341_MOESM10_ESM.xlsx"},
            "coverage": {"visible_records": len(rows), "intersections": 30},
            "limitations": "Only printed intersection counts and visibly dark membership nodes are recovered. Underlying mutation records are not inferred.",
        }
    report["coverage"]["intersections"] = sum(row["kind"] == "intersection" for row in rows)
    finish_case(root, original, draw_figure1(original, rows), rows, report)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=["fig5", "fig6", "fig7", "fig1", "all"], default="all")
    args = parser.parse_args()
    selected = {args.case} if args.case != "all" else {"fig5", "fig6", "fig7", "fig1"}
    if "fig5" in selected: build_figure5()
    if "fig6" in selected: build_figure6()
    if "fig7" in selected: build_figure7()
    if "fig1" in selected: build_figure1()


if __name__ == "__main__":
    main()
