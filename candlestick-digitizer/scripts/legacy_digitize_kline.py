"""Candlestick-chart digitizer - extract OHLC data from candlestick chart images.

Design: color masks -> bearish via vertical-projection peaks, bullish via peaks on
outline projection with multi-column body sampling. Shadow search spans the full
detected candle width.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def parse_color(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if "," in text:
        return tuple(int(p.strip()) for p in text.split(","))
    if len(text) != 6:
        raise ValueError("hex colors must be #RRGGBB")
    return tuple(int(text[i:i+2], 16) for i in range(0, 6, 2))


def parse_bounds(value: str) -> tuple[int, int, int, int]:
    vals = tuple(int(p.strip()) for p in value.split(","))
    if len(vals) != 4 or vals[0] >= vals[2] or vals[1] >= vals[3]:
        raise ValueError("bounds must be x0,y0,x1,y1")
    return vals


def color_mask_multi(pixels, colors, tolerance):
    mask = np.zeros(pixels.shape[:2], dtype=bool)
    for color in colors:
        target = np.asarray(color, dtype=np.int32)
        dist_sq = np.square(pixels.astype(np.int32) - target).sum(axis=2)
        mask |= dist_sq <= tolerance * tolerance
    return mask


def find_peaks(projection, min_height, min_distance=30, min_width=5, max_width=120):
    window = 3
    smoothed = np.convolve(projection, np.ones(window)/window, mode='same')
    above = smoothed > min_height

    regions = []
    in_region = False
    start = 0
    for i, ok in enumerate(above):
        if ok and not in_region:
            in_region = True
            start = i
        elif not ok and in_region:
            in_region = False
            regions.append((start, i - 1))
    if in_region:
        regions.append((start, len(above) - 1))

    def make_peak(s, e):
        peak_proj = smoothed[s:e+1]
        center = s + int(np.argmax(peak_proj))
        return {"center": center, "left": s, "right": e,
                "height": int(peak_proj.max()), "width": e - s + 1}

    def split_by_local_maxima(rs, re):
        seg = smoothed[rs:re+1]
        loc_max = [(rs + i, seg[i]) for i in range(1, len(seg) - 1)
                   if seg[i] > seg[i-1] and seg[i] >= seg[i+1]]
        loc_max.sort(key=lambda x: x[1], reverse=True)
        selected = []
        for idx, h in loc_max:
            if all(abs(idx - s) >= min_distance for s in selected):
                selected.append(idx)
        selected.sort()
        sub_peaks = []
        for idx in selected:
            ph = smoothed[idx]
            half = ph * 0.5
            left = idx
            while left > rs and smoothed[left] >= half:
                left -= 1
            right = idx
            while right < re and smoothed[right] >= half:
                right += 1
            w = right - left + 1
            if min_width <= w <= max_width:
                sub_peaks.append({"center": idx, "left": left, "right": right,
                                  "height": int(ph), "width": w})
        return sub_peaks

    peaks = []
    for rs, re in regions:
        width = re - rs + 1
        if width < min_width:
            continue
        if width <= max_width:
            peaks.append(make_peak(rs, re))
        else:
            sub_proj = smoothed[rs:re+1]
            region_max = sub_proj.max()
            threshold = region_max * 0.25
            valley = sub_proj < threshold
            split_pts = []
            in_valley = False
            v_start = 0
            for i, v in enumerate(valley):
                if v and not in_valley:
                    in_valley = True
                    v_start = i
                elif not v and in_valley:
                    in_valley = False
                    if v_start > 3 and i - 1 < width - 3:
                        split_pts.append(rs + (v_start + i - 1) // 2)
            if in_valley and v_start > 3 and v_start < width - 3:
                split_pts.append(rs + (v_start + width - 1) // 2)

            if split_pts:
                boundaries = [rs] + split_pts + [re + 1]
                for i in range(len(boundaries) - 1):
                    s, e = boundaries[i], boundaries[i+1] - 1
                    if min_width <= e - s + 1 <= max_width:
                        peaks.append(make_peak(s, e))
            else:
                sub_peaks = split_by_local_maxima(rs, re)
                peaks.extend(sub_peaks)

    if not peaks:
        return []

    peaks.sort(key=lambda p: p["center"])
    merged = [peaks[0]]
    for p in peaks[1:]:
        last = merged[-1]
        if p["center"] - last["center"] < min_distance:
            if p["height"] > last["height"]:
                merged[-1] = p
        else:
            merged.append(p)
    return merged


def analyze_column(mask, x, y0, y1, is_solid):
    col = mask[y0:y1+1, x]
    rows = np.where(col)[0] + y0
    if len(rows) < 2:
        return None
    diffs = np.diff(rows)
    breaks = np.where(diffs > (4 if is_solid else 5))[0]
    if len(breaks) > 0:
        segments = []
        start = 0
        for b in breaks:
            segments.append(rows[start:b+1])
            start = b + 1
        segments.append(rows[start:])
        largest = max(segments, key=len)
        body_top, body_bottom = int(largest[0]), int(largest[-1])
    else:
        body_top, body_bottom = int(rows.min()), int(rows.max())
    return {
        "y_body_top": body_top,
        "y_body_bottom": body_bottom,
        "y_shadow_top": int(rows.min()),
        "y_shadow_bottom": int(rows.max()),
        "pixel_count": int(len(rows)),
    }


def find_shadow_range(mask, x_left, x_right, y0, y1):
    """Find the full Y range of any matching pixels across [x_left, x_right]."""
    sub = mask[y0:y1+1, x_left:x_right+1]
    rows = np.where(sub)[0] + y0
    if len(rows) == 0:
        return None
    return {"y_shadow_top": int(rows.min()), "y_shadow_bottom": int(rows.max())}


def find_bullish_body(outline_mask, cx, y0, y1):
    """Find body/shadow geometry for a thin-outline bullish candle."""
    best_geo = None
    best_x = cx
    for dx in [0, -1, 1, -2, 2, -3, 3]:
        geo = analyze_column(outline_mask, cx + dx, y0, y1, is_solid=False)
        if geo:
            if not best_geo or geo["pixel_count"] > best_geo["pixel_count"]:
                best_geo = geo
                best_x = cx + dx
    if not best_geo:
        return None
    shadow = find_shadow_range(outline_mask, best_x - 15, best_x + 15, y0, y1)
    if shadow:
        best_geo["y_shadow_top"] = shadow["y_shadow_top"]
        best_geo["y_shadow_bottom"] = shadow["y_shadow_bottom"]
    return best_geo


def detect_bullish_candles(outline_mask, plot_bounds, y0, y1):
    """Detect bullish (outline) candles via peak detection on vertical projection."""
    x0, _, x1, _ = plot_bounds
    plot_o = outline_mask[y0:y1+1, x0:x1+1]
    proj = plot_o.sum(axis=0)
    peaks = find_peaks(proj, min_height=3, min_distance=60, min_width=3, max_width=60)

    candles = []
    for p in peaks:
        cx = x0 + p["center"]
        geo = find_bullish_body(outline_mask, cx, y0, y1)
        if not geo or geo["pixel_count"] < 2:
            continue

        candles.append({
            "x_center": float(cx),
            "x_left": int(x0 + p["left"]),
            "x_right": int(x0 + p["right"]),
            "width_px": int(p["width"]),
            "type": "bullish",
            **geo,
            "confidence": "high" if geo["pixel_count"] > 15 else "medium",
        })
    return candles


def detect_bearish_candles(body_mask, plot_bounds, y0, y1):
    """Detect bearish (solid) candles via peak detection with width-aware shadow search."""
    x0, _, x1, _ = plot_bounds
    plot_b = body_mask[y0:y1+1, x0:x1+1]
    proj_b = plot_b.sum(axis=0)
    peaks_b = find_peaks(proj_b, min_height=8, min_distance=40, min_width=5, max_width=120)

    candles = []
    for p in peaks_b:
        cx = x0 + p["center"]
        geo = analyze_column(body_mask, cx, y0, y1, is_solid=True)
        if not geo or geo["pixel_count"] < 8:
            continue

        # Refine left/right by walking from center until 2 consecutive empty cols
        left = cx
        empty = 0
        while left > x0 + 1:
            if body_mask[y0:y1+1, left - 1].sum() == 0:
                empty += 1
                if empty >= 2:
                    break
            else:
                empty = 0
            left -= 1
        right = cx
        empty = 0
        while right < x1 - 1:
            if body_mask[y0:y1+1, right + 1].sum() == 0:
                empty += 1
                if empty >= 2:
                    break
            else:
                empty = 0
            right += 1

        # Expand shadow search across the refined width
        shadow = find_shadow_range(body_mask, left, right, y0, y1)
        if shadow:
            geo["y_shadow_top"] = shadow["y_shadow_top"]
            geo["y_shadow_bottom"] = shadow["y_shadow_bottom"]

        candles.append({
            "x_center": float(cx),
            "x_left": int(left),
            "x_right": int(right),
            "width_px": int(right - left + 1),
            "type": "bearish",
            **geo,
            "confidence": "high" if geo["pixel_count"] > 50 else "medium",
        })
    return candles
def detect_klines(pixels, plot_bounds, bearish_colors, bullish_colors, tolerance):
    x0, y0, x1, y1 = plot_bounds
    body_mask = color_mask_multi(pixels, bearish_colors, tolerance)
    outline_mask = color_mask_multi(pixels, bullish_colors, tolerance)

    bearish = detect_bearish_candles(body_mask, plot_bounds, y0, y1)
    bullish = detect_bullish_candles(outline_mask, plot_bounds, y0, y1)

    print(f"Bearish: {len(bearish)}, Bullish: {len(bullish)}")
    for c in bearish:
        print(f"  bearish x={c['x_center']:.0f} w={c['width_px']} px={c['pixel_count']}")
    for c in bullish:
        print(f"  bullish x={c['x_center']:.0f} w={c['width_px']} px={c['pixel_count']}")

    candles = bearish + bullish
    candles.sort(key=lambda c: c["x_center"])

    # Merge nearby duplicates
    merged = []
    for c in candles:
        if not merged:
            merged.append(c)
            continue
        last = merged[-1]
        if abs(c["x_center"] - last["x_center"]) < 15:
            if c["pixel_count"] > last["pixel_count"]:
                merged[-1] = c
        else:
            merged.append(c)
    return merged


def to_serializable(obj):
    """Recursively convert numpy types to Python native types for JSON."""
    if isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_serializable(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def file_sha256(path):
    d = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            d.update(chunk)
    return d.hexdigest()


def calibrate(candles, y_px_min, y_val_min, y_px_max, y_val_max):
    results = []
    for c in candles:
        high = y_val_min + (c["y_shadow_top"] - y_px_min) * (y_val_max - y_val_min) / (y_px_max - y_px_min)
        low = y_val_min + (c["y_shadow_bottom"] - y_px_min) * (y_val_max - y_val_min) / (y_px_max - y_px_min)
        if c["type"] == "bearish":
            open_p = y_val_min + (c["y_body_top"] - y_px_min) * (y_val_max - y_val_min) / (y_px_max - y_px_min)
            close_p = y_val_min + (c["y_body_bottom"] - y_px_min) * (y_val_max - y_val_min) / (y_px_max - y_px_min)
        else:
            open_p = y_val_min + (c["y_body_bottom"] - y_px_min) * (y_val_max - y_val_min) / (y_px_max - y_px_min)
            close_p = y_val_min + (c["y_body_top"] - y_px_min) * (y_val_max - y_val_min) / (y_px_max - y_px_min)
        results.append({**c, "open": round(open_p, 3), "high": round(high, 3),
                        "low": round(low, 3), "close": round(close_p, 3)})
    return results


def create_overlay(image, candles, output):
    overlay = image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    for i, c in enumerate(candles):
        x = int(round(c["x_center"]))
        color = (0, 255, 255) if c["type"] == "bearish" else (255, 80, 80)
        body_color = (0, 180, 180) if c["type"] == "bearish" else (200, 60, 60)
        draw.line([(x, c["y_shadow_top"]), (x, c["y_shadow_bottom"])], fill=color, width=2)
        xl = c.get("x_left", x-8)
        xr = c.get("x_right", x+8)
        draw.rectangle([xl, c["y_body_top"], xr, c["y_body_bottom"]], outline=body_color, width=2)
        draw.ellipse((x-3, c["y_shadow_top"]-3, x+3, c["y_shadow_top"]+3), fill=(255, 255, 0))
        draw.ellipse((x-3, c["y_shadow_bottom"]-3, x+3, c["y_shadow_bottom"]+3), fill=(255, 255, 0))
        draw.text((xl, c["y_shadow_top"]-18), f"{i+1}", fill=(255, 255, 0))
    overlay.save(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--plot-bounds", required=True, type=parse_bounds)
    parser.add_argument("--y-px-min", required=True, type=float)
    parser.add_argument("--y-value-min", required=True, type=float)
    parser.add_argument("--y-px-max", required=True, type=float)
    parser.add_argument("--y-value-max", required=True, type=float)
    parser.add_argument("--bearish-colors", required=True, type=str)
    parser.add_argument("--bullish-colors", required=True, type=str)
    parser.add_argument("--color-tolerance", type=float, default=40.0)
    args = parser.parse_args()

    bc = [parse_color(c.strip()) for c in args.bearish_colors.split(",")]
    boc = [parse_color(c.strip()) for c in args.bullish_colors.split(",")]

    image = Image.open(args.input).convert("RGB")
    pixels = np.asarray(image)
    w, h = image.size
    x0, y0, x1, y1 = args.plot_bounds
    if not (0 <= x0 < x1 < w and 0 <= y0 < y1 < h):
        raise SystemExit(f"plot bounds must fit {w}x{h}")

    candles = detect_klines(pixels, args.plot_bounds, bc, boc, args.color_tolerance)
    candles = calibrate(candles, args.y_px_min, args.y_value_min, args.y_px_max, args.y_value_max)

    print(f"\nFinal: {len(candles)} candles")
    for c in candles:
        print(f"  x={c['x_center']:.0f} {c['type']} O={c['open']:.3f} H={c['high']:.3f} L={c['low']:.3f} C={c['close']:.3f}")

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "index", "x_center", "type", "open", "high", "low", "close",
            "y_body_top", "y_body_bottom", "y_shadow_top", "y_shadow_bottom",
            "width_px", "pixel_count", "confidence"
        ])
        writer.writeheader()
        for i, c in enumerate(candles, 1):
            writer.writerow({"index": i, "x_center": round(c["x_center"], 1), "type": c["type"],
                             "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"],
                             "y_body_top": c["y_body_top"], "y_body_bottom": c["y_body_bottom"],
                             "y_shadow_top": c["y_shadow_top"], "y_shadow_bottom": c["y_shadow_bottom"],
                             "width_px": c["width_px"], "pixel_count": c["pixel_count"],
                             "confidence": c["confidence"]})

    report = {
        "schema_version": 8,
        "input_file": args.input.name,
        "input_sha256": file_sha256(args.input),
        "image_size": {"width": w, "height": h},
        "plot_bounds_px": {"left": x0, "top": y0, "right": x1, "bottom": y1},
        "calibration": {"y": {"px_min": args.y_px_min, "value_min": args.y_value_min,
                              "px_max": args.y_px_max, "value_max": args.y_value_max}},
        "candles": candles, "candle_count": len(candles),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(to_serializable(report), ensure_ascii=False, indent=2), encoding="utf-8")

    if args.overlay:
        args.overlay.parent.mkdir(parents=True, exist_ok=True)
        create_overlay(image, candles, args.overlay)
    print(f"CSV={args.output_csv}")
    print(f"REPORT={args.report}")


if __name__ == "__main__":
    main()
