"""Deterministic source data and case definitions for synthetic candlestick benchmarks."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import math
import random
from typing import Iterable


def _business_dates(count: int) -> list[str]:
    current = date(2026, 1, 5)
    values: list[str] = []
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current.isoformat())
        current += timedelta(days=1)
    return values


def generate_ohlc(seed: int, count: int) -> list[dict]:
    """Generate a repeatable, visibly varied OHLC sequence."""
    if count < 2:
        raise ValueError("count must be at least 2")
    rng = random.Random(seed)
    dates = _business_dates(count)
    previous_close = 100.0 + (seed % 9)
    rows: list[dict] = []
    for index, time in enumerate(dates):
        drift = 0.42 * math.sin((index + seed % 5) / 2.7)
        open_price = previous_close + rng.uniform(-1.1, 1.1)
        change = drift + rng.uniform(-2.0, 2.0)
        if abs(change) < 0.22:
            change = 0.32 if index % 2 == 0 else -0.32
        close_price = open_price + change
        upper = rng.uniform(0.35, 1.65)
        lower = rng.uniform(0.35, 1.65)
        row = {
            "time": time,
            "open": round(open_price, 4),
            "high": round(max(open_price, close_price) + upper, 4),
            "low": round(min(open_price, close_price) - lower, 4),
            "close": round(close_price, 4),
        }
        rows.append(row)
        previous_close = close_price
    return rows


def simple_moving_average(rows: Iterable[dict], period: int) -> list[dict]:
    rows = list(rows)
    if period < 1:
        raise ValueError("period must be positive")
    result: list[dict] = []
    for index in range(period - 1, len(rows)):
        window = rows[index - period + 1 : index + 1]
        value = sum(float(row["close"]) for row in window) / period
        result.append({"time": rows[index]["time"], "value": round(value, 6)})
    return result


def bollinger_bands(rows: Iterable[dict], period: int, multiplier: float) -> dict[str, list[dict]]:
    rows = list(rows)
    if period < 2:
        raise ValueError("period must be at least 2")
    if multiplier <= 0:
        raise ValueError("multiplier must be positive")
    result = {"upper": [], "middle": [], "lower": []}
    for index in range(period - 1, len(rows)):
        window = [float(row["close"]) for row in rows[index - period + 1 : index + 1]]
        mean = sum(window) / period
        deviation = math.sqrt(sum((value - mean) ** 2 for value in window) / period)
        time = rows[index]["time"]
        result["upper"].append({"time": time, "value": round(mean + multiplier * deviation, 6)})
        result["middle"].append({"time": time, "value": round(mean, 6)})
        result["lower"].append({"time": time, "value": round(mean - multiplier * deviation, 6)})
    return result


PALETTES = {
    "western_light": {
        "background": "#FFFFFF",
        "text": "#333333",
        "grid": "#E6E8EB",
        "up": "#26A69A",
        "down": "#EF5350",
        "rise_direction": "close_above_open",
    },
    "western_dark": {
        "background": "#121722",
        "text": "#D1D4DC",
        "grid": "#2A2E39",
        "up": "#22AB94",
        "down": "#F7525F",
        "rise_direction": "close_above_open",
    },
    "chinese_light": {
        "background": "#FFFFFF",
        "text": "#262626",
        "grid": "#E8E8E8",
        "up": "#E64646",
        "down": "#00A884",
        "rise_direction": "close_above_open",
    },
    "chinese_dark": {
        "background": "#171A21",
        "text": "#D8D8D8",
        "grid": "#323640",
        "up": "#FF5B5B",
        "down": "#20C997",
        "rise_direction": "close_above_open",
    },
}


def _case(number: int, slug: str, family: str, **updates) -> dict:
    base = {
        "case_id": f"synthetic_lwc_{number:03d}_{slug}",
        "family": family,
        "classification": "clean",
        "seed": 1000 + number,
        "count": 18,
        "width": 1200,
        "height": 700,
        "palette": "western_light",
        "body_style": "filled",
        "geometry": "standard",
        "overlays": [],
        "near_color_overlay": False,
        "description": slug.replace("_", " "),
    }
    base.update(updates)
    return base


def case_definitions() -> list[dict]:
    """Return the fixed 4x4 benchmark coverage matrix."""
    cases = [
        _case(1, "light_western", "base"),
        _case(2, "dark_western", "base", palette="western_dark"),
        _case(3, "light_chinese", "base", palette="chinese_light"),
        _case(4, "hollow_chinese", "base", palette="chinese_light", body_style="hollow_rise", classification="stress"),
        _case(5, "doji", "geometry", palette="chinese_light", geometry="doji", classification="stress"),
        _case(6, "no_upper_wick", "geometry", geometry="no_upper_wick", classification="stress"),
        _case(7, "no_lower_wick", "geometry", palette="western_dark", geometry="no_lower_wick", classification="stress"),
        _case(8, "dense", "geometry", count=36, width=1000, height=620, classification="stress"),
        _case(9, "single_ma", "ma", classification="stress", overlays=[{"kind": "ma", "period": 5, "color": "#2962FF", "width": 2}]),
        _case(10, "dual_ma", "ma", palette="chinese_light", classification="stress", overlays=[
            {"kind": "ma", "period": 4, "color": "#7B61FF", "width": 2},
            {"kind": "ma", "period": 9, "color": "#F5A623", "width": 2},
        ]),
        _case(11, "dual_ma_cross", "ma", count=28, classification="stress", overlays=[
            {"kind": "ma", "period": 3, "color": "#00BCD4", "width": 3},
            {"kind": "ma", "period": 7, "color": "#FF9800", "width": 3},
        ]),
        _case(12, "near_color_ma", "ma", palette="chinese_light", classification="stress", near_color_overlay=True, overlays=[
            {"kind": "ma", "period": 4, "color": "#E85A5A", "width": 3},
        ]),
        _case(13, "bollinger_light", "bollinger", classification="stress", overlays=[{
            "kind": "bollinger", "period": 6, "multiplier": 2.0, "width": 2,
            "colors": {"upper": "#2962FF", "middle": "#AB47BC", "lower": "#2962FF"},
        }]),
        _case(14, "bollinger_dark", "bollinger", palette="western_dark", classification="stress", overlays=[{
            "kind": "bollinger", "period": 6, "multiplier": 2.0, "width": 2,
            "colors": {"upper": "#FFD54F", "middle": "#FF8A65", "lower": "#FFD54F"},
        }]),
        _case(15, "narrow_bollinger", "bollinger", count=28, classification="stress", overlays=[{
            "kind": "bollinger", "period": 4, "multiplier": 0.75, "width": 3,
            "colors": {"upper": "#00ACC1", "middle": "#8E24AA", "lower": "#00ACC1"},
        }]),
        _case(16, "lowres_combined", "bollinger", palette="chinese_dark", count=24, width=640, height=360, classification="stress", overlays=[
            {"kind": "ma", "period": 3, "color": "#FFD740", "width": 2},
            {"kind": "ma", "period": 8, "color": "#40C4FF", "width": 2},
            {"kind": "bollinger", "period": 6, "multiplier": 1.25, "width": 2,
             "colors": {"upper": "#B388FF", "middle": "#FFAB40", "lower": "#B388FF"}},
        ]),
    ]
    return deepcopy(cases)


def apply_geometry(rows: list[dict], geometry: str) -> list[dict]:
    """Apply a declared visible geometry stressor without breaking OHLC invariants."""
    result = deepcopy(rows)
    if geometry == "standard":
        return result
    selected = range(2, len(result), 5)
    for index in selected:
        row = result[index]
        if geometry == "doji":
            row["close"] = row["open"]
        elif geometry == "no_upper_wick":
            row["high"] = max(row["open"], row["close"])
        elif geometry == "no_lower_wick":
            row["low"] = min(row["open"], row["close"])
        else:
            raise ValueError(f"unknown geometry: {geometry}")
    return result
