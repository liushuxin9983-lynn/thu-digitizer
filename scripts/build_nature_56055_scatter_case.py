"""Build the Fig. 3c raster-only scatter-line gallery case.

The input is the retained Nature Communications raster.  Curve samples are
calibrated with ``digitize_line_chart.py`` and the local cyan/green dot fields
are measured as connected components.  No workbook or article source values
are read by this builder.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".tmp" / "nature-56055" / "figure3-complete.png"
WORK = ROOT / ".tmp" / "nature-56055"
OUT = ROOT / "gallery" / "assets" / "cases" / "nature-56055-fig3c"
CROP = (0, 600, 1495, 1878)
FONT = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")


CURVES = [
    ("Spontaneous curvature", "scatter-c-red4-report.json", "#fb8177", 635, 673, 975),
    ("Surface reconstruction", "scatter-c-blue4-report.json", "#2ba3ca", 976, 1013, 1314),
    ("Rigid", "scatter-c-gray-sample-report.json", "#808080", 1315, 1351, 1655),
]
MATRIX_ROIS = [(330, 820, 750, 930), (330, 1130, 750, 1310), (330, 1440, 750, 1580)]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT), size)


def curve_rows() -> list[dict]:
    rows: list[dict] = []
    for series, report_name, colour, panel_top, tick_top, tick_bottom in CURVES:
        report = json.loads((WORK / report_name).read_text(encoding="utf-8"))
        observed = report["samples"][series]
        previous: dict | None = None
        for index, item in enumerate(observed):
            value = item.get("value")
            if value is None:
                previous = None
                continue
            x_value = index * 2.5
            pixel_x = 142 + x_value * (1287 - 142) / 135
            pixel_y = tick_bottom - (float(value) - 3.3) * (tick_bottom - tick_top) / 0.4
            point = {
                "kind": "point",
                "series": series,
                "category": "visible curve marker",
                "x": round(x_value, 3),
                "value": round(float(value), 6),
                "pixel_x": round(pixel_x, 3),
                "pixel_y": round(pixel_y - CROP[1], 3),
                "radius": 7,
                "fill": colour,
                "confidence": item.get("confidence", 0),
                "value_status": "calibrated_raster_trace",
            }
            rows.append(point)
            if previous is not None:
                rows.append(
                    {
                        "kind": "line",
                        "series": series,
                        "category": "visible curve connection",
                        "x": previous["x"],
                        "value": "visible path",
                        "pixel_x": previous["pixel_x"],
                        "pixel_y": previous["pixel_y"],
                        "x2": point["pixel_x"],
                        "y2": point["pixel_y"],
                        "fill": "none",
                        "stroke": colour,
                        "stroke_width": 2,
                        "value_status": "raster_supported_connection",
                    }
                )
            previous = point
    return rows


def matrix_rows(image: Image.Image) -> list[dict]:
    rgb = np.asarray(image.convert("RGB"))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = (hsv[:, :, 0] >= 45) & (hsv[:, :, 0] <= 105) & (hsv[:, :, 1] >= 50) & (hsv[:, :, 2] >= 80)
    rows: list[dict] = []
    for panel_index, (left, top, right, bottom) in enumerate(MATRIX_ROIS, start=1):
        count, labels, stats, centres = cv2.connectedComponentsWithStats(mask[top:bottom, left:right].astype("uint8"), 8)
        for component in range(1, count):
            area = int(stats[component, cv2.CC_STAT_AREA])
            if not 100 <= area <= 800:
                continue
            cx, cy = centres[component]
            ys, xs = np.where(labels == component)
            colours = rgb[top + ys, left + xs]
            r, g, b = np.median(colours, axis=0).astype(int)
            rows.append(
                {
                    "kind": "point",
                    "series": f"local dot field {panel_index}",
                    "category": "visible cyan/green dot",
                    "x": "not axis-calibrated",
                    "value": "colour/radius only",
                    "pixel_x": round(float(left + cx), 3),
                    "pixel_y": round(float(top + cy - CROP[1]), 3),
                    "radius": round(math.sqrt(area / math.pi), 3),
                    "fill": f"#{r:02x}{g:02x}{b:02x}",
                    "confidence": round(min(0.98, area / 500), 3),
                    "value_status": "raster_component_geometry",
                }
            )
    return rows


def base_style() -> tuple[list[dict], list[dict], list[dict]]:
    lines: list[dict] = []
    annotations: list[dict] = []
    rects = [
        {"x": 1028, "y": 35, "width": 154, "height": 341, "fill": "#f8c8c8"},
        {"x": 913, "y": 376, "width": 322, "height": 339, "fill": "#cdeefa"},
        {"x": 937, "y": 715, "width": 333, "height": 341, "fill": "#cfcfcf"},
    ]
    colours = ["#fb8177", "#2ba3ca", "#808080"]
    names = ["Spontaneous curvature", "Surface reconstruction", "Rigid"]
    dashed = [182, 514, 885]
    for index, top in enumerate((35, 376, 715)):
        bottom = top + (341 if index != 1 else 339)
        lines.extend(
            [
                {"x1": 142, "y1": top, "x2": 142, "y2": bottom, "width": 2},
                {"x1": 142, "y1": bottom, "x2": 1297, "y2": bottom, "width": 2},
                {"x1": 142, "y1": dashed[index], "x2": 1297, "y2": dashed[index], "width": 1.5, "stroke": colours[index], "dash": "5 6"},
            ]
        )
        for tick in range(0, 136, 5):
            px = 142 + tick * (1287 - 142) / 135
            lines.append({"x1": px, "y1": bottom, "x2": px, "y2": bottom - (20 if tick % 10 == 0 else 10), "width": 2})
        for tick in (3.3, 3.4, 3.5, 3.6, 3.7):
            py = bottom - (tick - 3.3) * (bottom - top) / 0.4
            lines.append({"x1": 142, "y1": py, "x2": 162, "y2": py, "width": 2})
            annotations.append({"text": f"{tick:.1f}", "x": 118, "y": py + 6, "size": 19, "anchor": "ra"})
        annotations.append({"text": names[index], "x": 186, "y": top + 38, "size": 24, "fill": "#111"})
        annotations.append({"text": "●", "x": 167, "y": top + 38, "size": 20, "fill": colours[index]})
    annotations.extend(
        [
            {"text": "Interlayer distance (Å)", "x": 38, "y": 560, "size": 20, "rotate": -90, "anchor": "ma"},
            {"text": "Distance (Å)", "x": 720, "y": 1210, "size": 20, "anchor": "ma"},
        ]
    )
    return rects, lines, annotations


def draw_recreation(size: tuple[int, int], rows: list[dict], rects: list[dict], lines: list[dict], annotations: list[dict]) -> Image.Image:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for rect in rects:
        draw.rectangle((rect["x"], rect["y"], rect["x"] + rect["width"], rect["y"] + rect["height"]), fill=rect["fill"])
    for line in lines:
        dash = line.get("dash")
        if dash:
            x = line["x1"]
            while x < line["x2"]:
                draw.line((x, line["y1"], min(x + 5, line["x2"]), line["y2"]), fill=line.get("stroke", "#222"), width=max(1, int(line.get("width", 1))))
                x += 11
        else:
            draw.line((line["x1"], line["y1"], line["x2"], line["y2"]), fill=line.get("stroke", "#222"), width=max(1, int(line.get("width", 1))))
    for row in rows:
        if row["kind"] == "line":
            draw.line((row["pixel_x"], row["pixel_y"], row["x2"], row["y2"]), fill=row["stroke"], width=int(row.get("stroke_width", 2)))
    for row in rows:
        if row["kind"] != "point":
            continue
        x, y, radius = row["pixel_x"], row["pixel_y"], row["radius"]
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=row["fill"])
    for item in annotations:
        f = font(int(item.get("size", 12)))
        if item.get("rotate"):
            layer = Image.new("RGBA", size, (255, 255, 255, 0))
            layer_draw = ImageDraw.Draw(layer)
            layer_draw.text((item["x"], item["y"]), item["text"], fill=item.get("fill", "#222"), font=f, anchor=item.get("anchor"))
            image.paste(layer.rotate(item["rotate"], center=(item["x"], item["y"]), resample=Image.Resampling.BICUBIC), mask=layer.rotate(item["rotate"], center=(item["x"], item["y"]), resample=Image.Resampling.BICUBIC))
        else:
            draw.text((item["x"], item["y"]), item["text"], fill=item.get("fill", "#222"), font=f, anchor=item.get("anchor"))
    return image


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Missing retained raster: {SOURCE}")
    for _, report_name, _, _, _, _ in CURVES:
        if not (WORK / report_name).is_file():
            raise SystemExit(f"Missing digitization report: {WORK / report_name}")
    original_full = Image.open(SOURCE).convert("RGB")
    original = original_full.crop(CROP)
    rows = curve_rows() + matrix_rows(original_full)
    rects, lines, annotations = base_style()
    recreation = draw_recreation(original.size, rows, rects, lines, annotations)
    OUT.mkdir(parents=True, exist_ok=True)
    original.save(OUT / "original.png")
    recreation.save(OUT / "recreated.png")
    Image.blend(original, recreation, 0.48).save(OUT / "overlay.png")
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with (OUT / "data.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    report = {
        "schema_version": 1,
        "case_id": "nature-56055-fig3c",
        "status": "visible_geometry_candidate",
        "route": "calibrated_raster_scatter_trace_plus_component_geometry",
        "input": {"file": SOURCE.name, "sha256": sha256(SOURCE), "crop": list(CROP)},
        "panel_mapping": "Fig. 3c: three calibrated scatter-line panels and three local cyan/green component fields.",
        "coverage": {"curve_samples_attempted": 165, "curve_markers_visible": sum(row["kind"] == "point" and row["category"] == "visible curve marker" for row in rows), "local_dot_components": sum(row["category"] == "visible cyan/green dot" for row in rows)},
        "source_data": {"used_for_recreation": False, "role": "not used"},
        "limitations": ["Only raster-supported curve positions and separable coloured components are retained.", "Occluded curve positions remain absent rather than being filled from article source data.", "The local cyan/green dot fields retain visible position, colour and radius, not a hidden numerical variable."],
    }
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
