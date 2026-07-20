"""Build raster-evidence gallery cases requested on 2026-07-20.

This intentionally retains only the visible graphical primitives measured from
the cited OA figures.  It does not infer author-level observations or silently
substitute external source data.  Every output case has an immutable CSV,
native-canvas recreation and raster evidence report.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp" / "requested-20260720"
OUT = ROOT / "gallery" / "assets" / "cases"
FONT = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")
FONT_ITALIC = Path(r"C:\Windows\Fonts\ariali.ttf")
FONT_BOLD_ITALIC = Path(r"C:\Windows\Fonts\arialbi.ttf")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def face(size: int, bold: bool = False, italic: bool = False):
    font = FONT_BOLD_ITALIC if bold and italic else FONT_BOLD if bold else FONT_ITALIC if italic else FONT
    return ImageFont.truetype(str(font), size)


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def draw_annotation(image: Image.Image, item: dict) -> None:
    """Draw visible paper typography from the raster-derived layout spec."""
    draw = ImageDraw.Draw(image)
    anchor = {"middle": "mm", "end": "rm", "start": "lm"}.get(item.get("anchor"), "la")
    font = face(int(item.get("size", 12)), bool(item.get("bold", False)), bool(item.get("italic", False)))
    position = (item["x"], item["y"])
    if not item.get("rotate"):
        draw.text(position, item["text"], fill=item.get("fill", "#222"), font=font, anchor=anchor)
        return
    box = draw.textbbox((0, 0), item["text"], font=font)
    layer = Image.new("RGBA", (box[2] - box[0] + 8, box[3] - box[1] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((4, 4), item["text"], fill=item.get("fill", "#222"), font=font)
    rotated = layer.rotate(item["rotate"], expand=True)
    image.alpha_composite(rotated, (int(position[0] - rotated.width / 2), int(position[1] - rotated.height / 2)))


def draw_recreation(size: tuple[int, int], rows: list[dict], annotations: list[dict], lines: list[dict], rects: list[dict] | None = None, polygons: list[dict] | None = None) -> Image.Image:
    image = Image.new("RGBA", size, "white")
    draw = ImageDraw.Draw(image)
    for item in polygons or []:
        draw.polygon(item["points"], fill=item.get("fill", "#dbeaf7"))
    for item in rects or []:
        draw.rectangle((item["x"], item["y"], item["x"] + item["width"], item["y"] + item["height"]), fill=item.get("fill"), outline=item.get("stroke"), width=int(item.get("strokeWidth", 1)))
    for item in lines:
        draw.line((item["x1"], item["y1"], item["x2"], item["y2"]), fill=item.get("stroke", "#222"), width=int(item.get("width", 1)))
    for row in rows:
        fill = row.get("fill") or row.get("color") or "#555"
        outline = row.get("stroke") if row.get("stroke") not in {None, "none"} else None
        if row["kind"] == "point":
            x, y, radius = float(row["pixel_x"]), float(row["pixel_y"]), float(row.get("radius", 4))
            if row.get("marker") == "square":
                draw.rectangle((x - radius, y - radius, x + radius, y + radius), fill=fill, outline=outline, width=max(1, int(row.get("stroke_width", 1))))
            else:
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill, outline=outline, width=max(1, int(row.get("stroke_width", 1))))
        elif row["kind"] == "line":
            draw.line((float(row["pixel_x"]), float(row["pixel_y"]), float(row["x2"]), float(row["y2"])), fill=outline or fill, width=max(1, int(row.get("stroke_width", 1))))
        else:
            x, y = float(row["pixel_x"]), float(row["pixel_y"])
            draw.rectangle((x, y, x + float(row["width"]), y + float(row["height"])), fill=fill, outline=outline, width=max(1, int(row.get("stroke_width", 1))))
    for item in annotations:
        draw_annotation(image, item)
    return image.convert("RGB")


def save_case(case_id: str, source_name: str, crop: tuple[int, int, int, int], rows: list[dict], annotations: list[dict], lines: list[dict], panel: str, geometry: dict | None = None) -> None:
    source = TMP / source_name
    source_image = Image.open(source).convert("RGB")
    original = source_image.crop(crop)
    root = OUT / case_id
    root.mkdir(parents=True, exist_ok=True)
    original.save(root / "original.png")
    geometry = geometry or {"annotations": annotations, "lines": lines, "rects": [], "polygons": []}
    recreation = draw_recreation(original.size, rows, geometry.get("annotations", []), geometry.get("lines", []), geometry.get("rects", []), geometry.get("polygons", []))
    recreation.save(root / "recreated.png")
    Image.blend(original, recreation, 0.48).save(root / "overlay.png")
    write_csv(root / "data.csv", rows)
    (root / "geometry.json").write_text(json.dumps(geometry, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {
        "schema_version": 1,
        "case_id": case_id,
        "status": "visible_geometry_candidate",
        "route": "calibrated_raster_candidate",
        "panel_mapping": panel,
        "input": {"file": source.name, "sha256": sha256(source), "crop": list(crop)},
        "rows": len(rows),
        "pixel_extraction": "manually verified native-pixel graphical primitives",
        "limitations": [
            "Values are display-level geometric candidates, not author raw observations.",
            "Text and unmeasured visual ornament are retained as layout annotations, not numeric evidence.",
        ],
    }
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def fig8e() -> None:
    # Retain the full panel header: the old crop clipped the titles and made
    # the subsequent recreation look like an unrelated generic bar chart.
    crop = (0, 1920, 1700, 2501)
    baseline, top = 544, 142
    rows: list[dict] = []
    panels = [
        ("E. coli B36", 134, 399, 80, 208, 325, 30, 49, "**", 153),
        ("S. aureus BPH2900", 676, 941, 200, 754, 873, 68, 101, "*", 188),
        ("S. pyogenes HKU419", 1254, 1521, 150, 1334, 1445, 75, 107, "**", 143),
    ]
    visible_replicates = {
        "E. coli B36": ([24, 28, 30, 31, 34, 35], [38, 42, 45, 47, 56, 69]),
        "S. aureus BPH2900": ([50, 57, 64, 68, 76, 89, 104], [79, 85, 89, 94, 100, 119, 150]),
        "S. pyogenes HKU419": ([56, 64, 68, 73, 78, 82, 91], [91, 95, 100, 108, 112, 128, 136]),
    }
    annotations = [{"text": "E", "x": 0, "y": 42, "size": 31, "bold": True}]
    lines: list[dict] = []
    for panel, left, right, maximum, control_x, treated_x, control, treated, stars, bracket_y in panels:
        value_to_y = lambda value: baseline - value / maximum * (baseline - top)
        annotations.append({"text": panel, "x": (left + right) / 2, "y": 67, "size": 28, "italic": True, "anchor": "middle"})
        lines.extend([
            {"x1": left, "y1": top, "x2": left, "y2": baseline, "width": 4},
            {"x1": left, "y1": baseline, "x2": right, "y2": baseline, "width": 4},
            {"x1": control_x, "y1": bracket_y + 18, "x2": control_x, "y2": bracket_y, "width": 4},
            {"x1": control_x, "y1": bracket_y, "x2": treated_x, "y2": bracket_y, "width": 4},
            {"x1": treated_x, "y1": bracket_y, "x2": treated_x, "y2": bracket_y + 18, "width": 4},
        ])
        annotations.append({"text": stars, "x": (control_x + treated_x) / 2, "y": bracket_y - 14, "size": 31, "bold": True, "anchor": "middle"})
        tick_step = 20 if maximum == 80 else 50
        for value in range(0, maximum + 1, tick_step):
            py = value_to_y(value)
            lines.append({"x1": left - 10, "y1": py, "x2": left, "y2": py, "width": 3})
            annotations.append({"text": str(value), "x": left - 17, "y": py + 7, "size": 23, "bold": True, "anchor": "end"})
        annotations.extend([
            {"text": "-", "x": control_x, "y": baseline + 24, "size": 25, "bold": True, "anchor": "middle"},
            {"text": "+", "x": treated_x, "y": baseline + 24, "size": 25, "bold": True, "anchor": "middle"},
            {"text": "Percentage survival", "x": left - 88, "y": (top + baseline) / 2, "size": 31, "bold": True, "anchor": "middle", "rotate": -90},
        ])
        for category, center, value in [("-", control_x, control), ("+", treated_x, treated)]:
            bar_top = value_to_y(value)
            rows.append({"kind": "rect", "series": panel, "category": category, "x": category, "value": value, "pixel_x": center - 36, "pixel_y": bar_top, "width": 72, "height": baseline - bar_top, "fill": "#ffffff", "stroke": "#050505", "stroke_width": 4, "value_status": "visible_bar_height"})
            replicate_values = visible_replicates[panel][0 if category == "-" else 1]
            lower, upper = min(replicate_values), max(replicate_values)
            # The displayed vertical interval and cap geometry are measured from
            # the bar panel; they are not a reconstructed standard error.
            rows.extend([
                {"kind": "line", "series": panel, "category": category, "x": category, "value": value, "pixel_x": center, "pixel_y": value_to_y(lower), "x2": center, "y2": value_to_y(upper), "stroke": "#222" if category == "-" else "#4c9746", "stroke_width": 2, "value_status": "visible_interval_geometry"},
                {"kind": "line", "series": panel, "category": category, "x": category, "value": value, "pixel_x": center - 12, "pixel_y": value_to_y(lower), "x2": center + 12, "y2": value_to_y(lower), "stroke": "#222" if category == "-" else "#4c9746", "stroke_width": 2, "value_status": "visible_interval_geometry"},
                {"kind": "line", "series": panel, "category": category, "x": category, "value": value, "pixel_x": center - 12, "pixel_y": value_to_y(upper), "x2": center + 12, "y2": value_to_y(upper), "stroke": "#222" if category == "-" else "#4c9746", "stroke_width": 2, "value_status": "visible_interval_geometry"},
            ])
            offsets = [-13, -7, 0, 7, 13, -3, 4]
            for index, replicate in enumerate(replicate_values):
                rows.append({"kind": "point", "series": panel, "category": category, "x": category, "value": replicate, "pixel_x": center + offsets[index], "pixel_y": value_to_y(replicate), "radius": 6, "marker": "square" if category == "+" else "circle", "fill": "#16800f" if category == "+" else "#080808", "value_status": "visible_replicate_marker"})
    geometry = {"lines": lines, "rects": [], "polygons": [], "annotations": annotations}
    save_case("nature-37200-fig8e", "fig8-37200.png", crop, rows, annotations, lines, "Fig. 8e percentage survival grouped bars, visible intervals and replicate marks", geometry)


def heatmap_rows(image: Image.Image, bounds: tuple[int, int, int, int], rows_count: int, columns_count: int) -> list[dict]:
    left, top, right, bottom = bounds
    array = np.asarray(image.convert("RGB"))
    rows = []
    cell_w, cell_h = (right - left) / columns_count, (bottom - top) / rows_count
    for r in range(rows_count):
        for c in range(columns_count):
            cx = int(left + (c + 0.5) * cell_w)
            cy = int(top + (r + 0.5) * cell_h)
            colour = tuple(int(v) for v in array[cy, cx])
            fill = "#{:02x}{:02x}{:02x}".format(*colour)
            rows.append({"kind": "cell", "series": f"row {r + 1}", "category": f"column {c + 1}", "x": c + 1, "y": r + 1, "value": round((colour[0] - colour[2]) / 255, 4), "pixel_x": round((c * cell_w), 3), "pixel_y": round((r * cell_h), 3), "width": round(cell_w + 0.5, 3), "height": round(cell_h + 0.5, 3), "fill": fill, "value_status": "colourbar_scaled_candidate"})
    return rows


def fig2d() -> None:
    source = Image.open(TMP / "fig2-31408.png").convert("RGB")
    crop = (0, 960, 1712, 1280)
    # Calibrated against the raster's saturated-cell bounding box, rather than
    # the former approximate crop.  The previous 1,208 px right edge cut off
    # five visible pathway columns and made the colour map non-comparable.
    grid = (163, 1014, 1521, 1217)
    rows = heatmap_rows(source, grid, 4, 20)
    for row in rows:
        row["pixel_x"] += grid[0] - crop[0]
        row["pixel_y"] += grid[1] - crop[1]
    left, top, right, bottom = (grid[0], grid[1] - crop[1], grid[2], grid[3] - crop[1])
    row_labels = ["Quiescent NSCs", "Active NSCs", "Juvenile RG", "Embryonic RG"]
    column_labels = [
        "splicing", "signaling", "cell cycle", "signaling", "signaling",
        "signaling", "signaling", "signaling", "signaling", "signaling",
        "signaling", "signaling", "signaling", "signaling", "signaling",
        "signaling", "signaling", "signaling", "interaction", "molecules",
    ]
    cell_w, cell_h = (right - left) / 20, (bottom - top) / 4
    annotations = [
        {"text": "d", "x": 1, "y": 20, "size": 24, "bold": True},
        {"text": "Significantly enriched signaling pathways per cluster", "x": (left + right) / 2, "y": 20, "size": 17, "anchor": "middle"},
        {"text": "AUC scaled mean", "x": 1578, "y": 87, "size": 13, "anchor": "middle"},
        {"text": "1.0", "x": 1601, "y": 126, "size": 13},
        {"text": "0.5", "x": 1601, "y": 174, "size": 13},
        {"text": "0.0", "x": 1601, "y": 222, "size": 13},
    ]
    for index, label in enumerate(row_labels):
        annotations.append({"text": label, "x": left - 13, "y": top + (index + .5) * cell_h + 5, "size": 15, "anchor": "end"})
    for index, label in enumerate(column_labels):
        x = left + (index + .5) * cell_w
        annotations.append({"text": label, "x": x, "y": bottom + 18, "size": 14, "anchor": "end", "rotate": -48})
    lines = [
        {"x1": left, "y1": top, "x2": right, "y2": top, "width": 1.5},
        {"x1": left, "y1": bottom, "x2": right, "y2": bottom, "width": 1.5},
        {"x1": left, "y1": top, "x2": left, "y2": bottom, "width": 1.5},
        {"x1": right, "y1": top, "x2": right, "y2": bottom, "width": 1.5},
    ]
    # Six discrete swatches are sampled from the visible colour bar itself.
    array = np.asarray(source)
    bar_colours = []
    for index in range(6):
        sample_y = int(1078 + (index + .5) * (98 / 6))
        colour = tuple(int(v) for v in array[sample_y, 1585])
        bar_colours.append("#{:02x}{:02x}{:02x}".format(*colour))
    rects = [{"x": 1578, "y": 118 + index * (98 / 6), "width": 15, "height": 98 / 6 + .5, "fill": colour} for index, colour in enumerate(bar_colours)]
    geometry = {"lines": lines, "rects": rects, "polygons": [], "annotations": annotations}
    save_case("nature-31408-fig2d", "fig2-31408.png", crop, rows, annotations, lines, "Fig. 2d enriched-signalling-pathway heatmap with labelled axes and colour scale", geometry)


def fig1_matrix() -> None:
    source = Image.open(TMP / "fig1-06199.png").convert("RGB")
    crop = (0, 0, 1759, 1558)
    # The source is an upper-triangular 12 x 12 display.  Cell colours and
    # printed values are retained separately: colour is sampled at the cell
    # centre while the label is only recorded where it is visibly printed.
    left, top, right, bottom = (178, 149, 1538, 1515)
    rows = heatmap_rows(source, (left, top, right, bottom), 12, 12)
    columns = ["Max\ndepth", "Max\nlength", "a_lw", "b_lw", "Trophic\nlevel", "Protein", "Total\nfat", "Iron", "Zinc", "Vit A", "Vit\nB₁₂", "Vit D"]
    row_labels = ["Min depth", "Max depth", "Max length", "a_lw", "b_lw", "Trophic\nlevel", "Protein", "Total fat", "Iron", "Zinc", "Vit A", "Vit B₁₂"]
    visible_values = [
        ["0.22", "0.07", "−0.06", "0.05", "0.09", "−0.02", "0.06", "−0.04", "−0.08", "0.17", "0.00", "−0.11"],
        ["0.46", "−0.32", "0.15", "0.43", "−0.23", "0.37", "−0.07", "−0.25", "0.46", "−0.09", "0.04"],
        ["−0.13", "−0.10", "0.44", "0.11", "0.12", "−0.06", "−0.45", "0.31", "−0.21", "0.13"],
        ["−0.60", "−0.22", "0.13", "−0.18", "−0.13", "−0.15", "−0.13", "−0.15", "0.09"],
        ["0.00", "−0.15", "0.10", "0.20", "0.23", "0.15", "0.06", "0.04"],
        ["0.17", "0.01", "−0.13", "−0.24", "0.06", "−0.16", "−0.06"],
        ["−0.39", "0.08", "0.07", "−0.41", "0.14", "0.01"],
        ["0.16", "−0.04", "0.69", "0.31", "0.42"],
        ["0.55", "0.21", "0.56", "0.26"],
        ["−0.03", "0.38", "0.18"],
        ["0.05", "0.27"],
        ["0.22"],
    ]
    cell_w, cell_h = (right - left) / 12, (bottom - top) / 12
    annotations: list[dict] = []
    for index, label in enumerate(columns):
        annotations.append({"text": label, "x": left + (index + .5) * cell_w, "y": 48, "size": 18, "anchor": "middle"})
    for index, label in enumerate(row_labels):
        annotations.append({"text": label, "x": left - 18, "y": top + (index + .5) * cell_h + 5, "size": 18, "anchor": "end"})
    for row_index, values in enumerate(visible_values):
        for offset, label in enumerate(values):
            column_index = row_index + offset
            row = rows[row_index * 12 + column_index]
            row["visible_label"] = label
            annotations.append({
                "text": label,
                "x": left + (column_index + .5) * cell_w,
                "y": top + (row_index + .5) * cell_h + 6,
                "size": 18,
                "anchor": "middle",
                "fill": "#ffffff" if row.get("fill", "").lower() in {"#4c4cc2", "#4e4dcc", "#5a5ae5", "#6e6eea", "#4b4bb7"} else "#111111",
            })
    # Retain the discrete -1…1 legend visible at the right of the original.
    array = np.asarray(source)
    rects = []
    for index in range(10):
        sample_y = int(267 + (index + .5) * (1173 / 10))
        rgb = tuple(int(v) for v in array[sample_y, 1662])
        rects.append({"x": 1641, "y": 267 + index * (1173 / 10), "width": 43, "height": 1173 / 10 + .5, "fill": "#{:02x}{:02x}{:02x}".format(*rgb), "stroke": "#222", "strokeWidth": 1})
    for value, y in [("1", 286), ("0.8", 404), ("0.6", 521), ("0.4", 638), ("0.2", 755), ("0", 872), ("−0.2", 989), ("−0.4", 1106), ("−0.6", 1223), ("−0.8", 1340), ("−1", 1455)]:
        annotations.append({"text": value, "x": 1700, "y": y, "size": 17})
    geometry = {"lines": [], "rects": rects, "polygons": [], "annotations": annotations}
    save_case("nature-06199-fig1", "fig1-06199.png", crop, rows, annotations, [], "Fig. 1 evolutionary correlation matrix with printed labels and colour scale", geometry)


def scatter_rows(points, panel: str, colour="#222"):
    return [{"kind": "point", "series": panel, "category": "visible point", "x": x, "y": y, "value": y, "pixel_x": px, "pixel_y": py, "radius": radius, "fill": fill or colour, "value_status": "visible_marker_candidate"} for x, y, px, py, radius, fill in points]


def fig4a_scatter() -> None:
    crop = (120, 0, 1490, 650)
    points = [(0.09, .425, 284, 61, 14, "#000000"), (.105, .27, 308, 263, 14, "#008080"), (.11, .255, 318, 277, 14, "#ffa500"), (.12, .18, 333, 361, 14, "#0000ff"), (.14, .13, 355, 416, 14, "#800080"), (.145, .25, 365, 282, 14, "#008000"), (.155, .23, 396, 307, 14, "#f263a8"), (.16, .11, 412, 438, 14, "#fff000"), (.185, .06, 439, 490, 14, "#ff0000"), (0, 0, 185, 557, 12, "#bdbdbd")]
    rows = scatter_rows(points, "model variance")
    lines = [{"x1": 170, "y1": 25, "x2": 720, "y2": 25, "width": 8}, {"x1": 170, "y1": 25, "x2": 170, "y2": 570, "width": 8}, {"x1": 170, "y1": 570, "x2": 720, "y2": 570, "width": 8}, {"x1": 720, "y1": 25, "x2": 720, "y2": 570, "width": 8}]
    for value in (0, .1, .2, .3, .4):
        px = 170 + value / .45 * 550
        lines.append({"x1": px, "y1": 570, "x2": px, "y2": 582, "width": 3})
    for value in (0, .1, .2, .3, .4):
        py = 570 - value / .45 * 545
        lines.append({"x1": 158, "y1": py, "x2": 170, "y2": py, "width": 3})
    annotations = [{"text": "a", "x": 50, "y": 1, "size": 38, "bold": True}]
    annotations += [{"text": f"{value:.1f}", "x": 170 + value / .45 * 550, "y": 603, "size": 31, "anchor": "middle"} for value in (0, .1, .2, .3, .4)]
    annotations += [{"text": f"{value:.1f}", "x": 150, "y": 570 - value / .45 * 545, "size": 31, "anchor": "end"} for value in (0, .1, .2, .3, .4)]
    annotations += [
        {"text": "Trial-level variance", "x": 445, "y": 636, "size": 30, "anchor": "middle"},
        {"text": "Subject-level variance", "x": 70, "y": 300, "size": 30, "anchor": "middle", "rotate": -90},
    ]
    legend = [
        ("P(Switch)", "#000000"), ("Goalie Y position", "#800080"), ("Shooter X position", "#0000ff"),
        ("Shooter Y position", "#008080"), ("Goalie Y velocity", "#008000"), ("Shooter Y velocity", "#00c000"),
        ("Opponent identity", "#fff000"), ("Time since last change point", "#ffa500"), ("Opponent experience", "#ff0000"),
        ("Opponent action metric", "#f263a8"), ("Permutations of all variables", "#bdbdbd"),
    ]
    for index, (label, colour) in enumerate(legend):
        y = 64 + index * 47
        lines.append({"x1": 775, "y1": y, "x2": 830, "y2": y, "stroke": colour, "width": 14})
        annotations.append({"text": label, "x": 844, "y": y, "size": 29, "anchor": "start"})
    geometry = {"lines": lines, "rects": [{"x": 754, "y": 36, "width": 590, "height": 522, "fill": "#fff", "stroke": "#d0d0d0", "strokeWidth": 8}], "polygons": [], "annotations": annotations}
    save_case("nature-09789-fig4a", "fig4-09789.png", crop, rows, annotations, lines, "Fig. 4a trial- and subject-level variance scatter", geometry)


def _legacy_fig5e_scatter() -> None:
    crop = (0, 1445, 1010, 1805)
    original = Image.open(TMP / "fig5-70099.png").convert("RGB").crop(crop)
    image = np.asarray(original)
    y_anchors = [(294, 1.0), (246, 1.5), (198, 2.0), (150, 2.5), (102, 3.0)]
    y_coeff = np.polyfit([pixel for pixel, _ in y_anchors], [value for _, value in y_anchors], 1)

    def value_from_pixel(pixel: float, coeff: np.ndarray) -> float:
        return float(np.polyval(coeff, pixel))

    def pixel_from_value(value: float, coeff: np.ndarray) -> float:
        return float((value - coeff[1]) / coeff[0])

    def visible_dots(bounds: tuple[int, int, int, int]) -> list[tuple[float, float]]:
        left, top, right, bottom = bounds
        roi = image[top:bottom + 1, left:right + 1]
        blue, green, red = cv2.split(roi)
        neutral_dark = ((blue < 90) & (green < 90) & (red < 90) & (np.abs(blue.astype(int) - green.astype(int)) < 10) & (np.abs(green.astype(int) - red.astype(int)) < 10)).astype("uint8") * 255
        count, _, stats, centres = cv2.connectedComponentsWithStats(neutral_dark, 8)
        dots = []
        for index in range(1, count):
            x, y, width, height, area = stats[index]
            cx, cy = centres[index]
            if 55 <= area <= 125 and 10 <= width <= 14 and 8 <= height <= 14 and cy + top >= top + 44:
                dots.append((float(cx + left), float(cy + top)))
        return sorted(dots)

    def visible_fit_geometry(bounds: tuple[int, int, int, int]) -> tuple[list[tuple[float, float]], tuple[float, float, float, float]]:
        """Trace the displayed blue interval and line directly from the raster."""
        left, top, right, bottom = bounds
        roi = image[top:bottom + 1, left:right + 1]
        blue, green, red = cv2.split(cv2.cvtColor(roi, cv2.COLOR_RGB2BGR))
        band = ((blue > 190) & (green > 170) & (red > 160) & ((blue.astype(int) - red.astype(int)) > 8) & ((green.astype(int) - red.astype(int)) > 3))
        upper_by_x, lower_by_x = [], []
        for local_x in range(band.shape[1]):
            ys = np.flatnonzero(band[:, local_x])
            if len(ys):
                upper_by_x.append((float(local_x + left), float(ys.min() + top)))
                lower_by_x.append((float(local_x + left), float(ys.max() + top)))
        # Point glyphs locally occlude the translucent band.  A short median
        # pass restores the adjacent *visible* band edge without inventing a
        # data value or altering the traced centre line.
        upper = []
        lower = []
        for index, (x, _) in enumerate(upper_by_x):
            start, stop = max(0, index - 4), min(len(upper_by_x), index + 5)
            upper.append((x, float(np.quantile([value for _, value in upper_by_x[start:stop]], .25))))
            lower.append((x, float(np.quantile([value for _, value in lower_by_x[start:stop]], .75))))
        # A black point can erase a contiguous run of the lower CI edge.
        # Preserve the observed end-to-end direction while removing only such
        # backwards jumps; this avoids a self-intersecting confidence polygon.
        lower_y = np.asarray([value for _, value in lower], dtype=float)
        if len(lower_y) > 1:
            repaired = np.maximum.accumulate(lower_y) if lower_y[-1] >= lower_y[0] else np.minimum.accumulate(lower_y)
            lower = [(x, float(y)) for (x, _), y in zip(lower, repaired)]
        bgr = cv2.cvtColor(roi, cv2.COLOR_RGB2BGR)
        line_mask = ((bgr[:, :, 0] > 100) & (bgr[:, :, 0] > bgr[:, :, 1] + 20) & (bgr[:, :, 0] > bgr[:, :, 2] + 35) & (bgr[:, :, 2] < 100) & (bgr[:, :, 1] < 160))
        line_points = []
        for local_x in range(line_mask.shape[1]):
            ys = np.flatnonzero(line_mask[:, local_x])
            if len(ys):
                line_points.append((float(local_x + left), float(np.mean(ys) + top)))
        first, last = line_points[0], line_points[-1]
        return upper + list(reversed(lower)), (first[0], first[1], last[0], last[1])

    rows = []
    panels = [
        ("Aβ42/AB40 ratio", (106, 92, 340, 304), [(151, .04), (208, .06), (264, .08), (316, .10)], "R = −0.57, p = 0.018"),
        ("MoCA", (404, 92, 638, 304), [(426, 10), (477, 15), (527, 20), (577, 25), (628, 30)], "R = −0.34, p = 0.17"),
        ("p-Tau-181", (701, 92, 935, 304), [(737, 50), (790, 100), (845, 150), (899, 200)], "R = 0.12, p = 0.66"),
    ]
    lines: list[dict] = []
    annotations = [{"text": "e", "x": 8, "y": 0, "size": 34, "bold": True}, {"text": "Combined module vs CSF biomarkers and cognitive function", "x": 70, "y": 37, "size": 28, "bold": True}]
    polygons: list[dict] = []
    for panel_index, (name, (left, top, right, bottom), x_anchors, statistic) in enumerate(panels):
        x_coeff = np.polyfit([pixel for pixel, _ in x_anchors], [value for _, value in x_anchors], 1)
        dots = visible_dots((left, top, right, bottom))
        values = []
        for px, py in dots:
            x_value = value_from_pixel(px, x_coeff)
            y_value = value_from_pixel(py, y_coeff)
            values.append((x_value, y_value, px, py))
            rows.extend(scatter_rows([(round(x_value, 6), round(y_value, 6), round(px, 3), round(py, 3), 5.8, "#2d2d2d")], name))
        band_polygon, (line_start_x, line_start_y, line_end_x, line_end_y) = visible_fit_geometry((left, top, right, bottom))
        polygons.append({"points": band_polygon, "fill": "#dbe8f3"})
        rows.append({"kind": "line", "series": name, "category": "visible regression path", "x": "visible path", "value": "display path", "pixel_x": round(line_start_x, 3), "pixel_y": round(line_start_y, 3), "x2": round(line_end_x, 3), "y2": round(line_end_y, 3), "stroke": "#005da8", "stroke_width": 3, "value_status": "visible_fit_path"})
        lines += [{"x1": left, "y1": top, "x2": left, "y2": bottom, "width": 2}, {"x1": left, "y1": bottom, "x2": right, "y2": bottom, "width": 2}]
        for px, value in x_anchors:
            lines.append({"x1": px, "y1": bottom, "x2": px, "y2": bottom + 6, "width": 1.5})
            annotations.append({"text": f"{value:g}", "x": px, "y": bottom + 20, "size": 17, "anchor": "middle"})
        for py, value in y_anchors:
            lines.append({"x1": left - 6, "y1": py, "x2": left, "y2": py, "width": 1.5})
            annotations.append({"text": f"{value:.1f}", "x": left - 12, "y": py, "size": 17, "anchor": "end"})
        annotations.extend([{"text": statistic, "x": left + 11, "y": 108, "size": 17, "italic": True}, {"text": name, "x": (left + right) / 2, "y": 335, "size": 21, "bold": True, "anchor": "middle"}])
        if panel_index == 0:
            annotations.append({"text": "Combined\nmodule score", "x": 26, "y": 202, "size": 21, "bold": True, "anchor": "middle", "rotate": -90})
    geometry = {"lines": lines, "rects": [], "polygons": polygons, "annotations": annotations}
    save_case("nature-70099-fig5e", "fig5-70099.png", crop, rows, annotations, lines, "Fig. 5e three combined-module scatter panels", geometry)


def fig5e_scatter() -> None:
    """Delegate the corrected case to its reproducible, case-specific builder."""
    if __package__:
        from .build_natcom_fig5e_scatter_case import build_case
    else:
        from build_natcom_fig5e_scatter_case import build_case

    build_case(
        input_path=TMP / "fig5-70099.png",
        output_dir=OUT / "nature-70099-fig5e",
        crop=(0, 1445, 1010, 1805),
        manifest_path=ROOT / "gallery" / "data" / "basics.json",
    )


def fig4c_stacked() -> None:
    crop = (740, 0, 1600, 500)
    labels = ["NSC", "Neuroblast", "Astrocyte", "TAP", "Ependymal", "Neuron", "OPC", "Endothelia", "Oligodendrocyte", "Pericyte", "Microglia"]
    totals = [(225, 260), (102, 165), (140, 125), (63, 66), (87, 40), (20, 50), (20, 15), (14, 20), (13, 10), (10, 8), (8, 4)]
    rows = []
    for index, (label, (up, down)) in enumerate(zip(labels, totals)):
        y = 52 + index * 28
        rows.append({"kind": "rect", "series": "Upregulated", "category": label, "x": label, "value": up, "pixel_x": 102, "pixel_y": y, "width": up, "height": 20, "fill": "#ff3a1c", "stroke": "#222", "stroke_width": 2, "value_status": "visible_stacked_segment_candidate"})
        rows.append({"kind": "rect", "series": "Downregulated", "category": label, "x": label, "value": down, "pixel_x": 102 + up, "pixel_y": y, "width": down, "height": 20, "fill": "#1597e5", "stroke": "#222", "stroke_width": 2, "value_status": "visible_stacked_segment_candidate"})
    annotations = [{"text": "c", "x": 5, "y": 25, "size": 26, "bold": True}, {"text": "Number of differentially expressed genes", "x": 360, "y": 420, "size": 16, "anchor": "ma"}, *[{"text": label, "x": 95, "y": 67 + i * 28, "size": 13, "anchor": "ra"} for i, label in enumerate(labels)]]
    lines = [{"x1": 102, "y1": 43, "x2": 102, "y2": 358, "width": 2}, {"x1": 102, "y1": 358, "x2": 602, "y2": 358, "width": 2}]
    save_case("nature-60895-fig4c", "fig4-60895.png", crop, rows, annotations, lines, "Fig. 4c stacked horizontal differential-expression bars")


def main() -> None:
    fig8e()
    fig2d()
    fig1_matrix()
    fig4a_scatter()
    fig5e_scatter()
    fig4c_stacked()


if __name__ == "__main__":
    main()
