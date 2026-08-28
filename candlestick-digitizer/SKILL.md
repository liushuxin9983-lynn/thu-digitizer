---
name: candlestick-digitizer
description: Load when the user asks to extract visible OHLC values from a candlestick chart image, digitize candle bodies and wicks, or validate a candlestick extraction against independent source data.
---

# Candlestick Chart Digitizer

Candlestick Chart Digitizer is an evidence-bound **candidate** extractor for color-distinct candlestick screenshots. It measures visible bodies and wicks at original resolution, maps pixel Y coordinates to a verified linear price axis, and writes an auditable evidence bundle.

It does not silently invent missing candles, hidden wick endpoints, dates, volume, moving-average values, or source trading records. Ambiguous geometry blocks numeric authorization.

## Runtime setup

Install the Python runtime dependencies once from the skill directory:

```powershell
python -m pip install -r scripts/requirements.txt
```

The basic raster extractor is then ready. Only install the optional pinned Node
renderer when generating synthetic Lightweight Charts benchmarks:

```powershell
npm --prefix scripts ci
npm exec --prefix scripts -- playwright install chromium
```

## Current maturity and recoverable representation

Maturity: `candidate`.

Recoverable when visibly supported:

- one left-to-right candle slot per accepted body;
- filled or outline body bounds in `original_raster_pixels`;
- upper and lower wick endpoints in `original_raster_pixels`;
- explicitly configured style semantics (`open_above_close` or `close_above_open`);
- calibrated Open, High, Low, and Close values on a verified linear price axis.

Not recoverable through this route:

- dates that are not individually printed and verified;
- volume, turnover, indicators, annotations, or hidden marks;
- raw exchange records or values not visibly encoded in the raster;
- log-price axes, gradient bodies, dense/fused candles, or unresolved multi-panel layouts.

## Required preflight

Before extraction, confirm and record:

1. The exact original image SHA-256, width, and height.
2. Plot bounds in `original_raster_pixels`.
3. Two source-pixel-evidenced tick anchors for a linear price axis.
4. One or more sampled colors and a tolerance for each visual style.
5. Whether each visual style means `open_above_close` or `close_above_open`; color alone never defines direction.
6. Plausible visible body-width bounds and wick center tolerance.
7. Any same-color distractor exclusion or verified differently colored occluder.

Refuse before numeric extraction when the source hash/dimensions, bounds, axis transform, anchors, or style semantics are unresolved.

**Price-anchor gotcha:** For a new real-raster case, set
`require_anchor_evidence: true` and require each anchor to use
`horizontal_reference_line` evidence. An anchor pixel is the associated
gridline or axis-tick plot row, never the printed label text center or baseline.
Use the verified row for calibration and retain the verified row adjustment in
the report. Refuse numeric output when the source pixels do not support the
declared horizontal reference.

## Configuration and extraction

Use a source-locked JSON configuration. A benchmark manifest may also be supplied; the CLI extracts only its `extraction_config` plus image contract and never passes benchmark truth to the detector.

```powershell
python scripts/digitize_kline.py `
  --input chart.png `
  --config extraction-config.json `
  --output-dir evidence
```

Minimal configuration shape:

```json
{
  "source_contract": {
    "sha256": "UPPERCASE_SHA256",
    "width": 1505,
    "height": 874
  },
  "plot_bounds": [4, 47, 1438, 830],
  "price_axis": {
    "scale": "linear",
    "require_anchor_evidence": true,
    "anchors": [
      {
        "pixel": 47,
        "value": 27.5,
        "evidence": {
          "kind": "horizontal_reference_line",
          "role": "gridline",
          "x_range": [4, 1438],
          "color": "#E6E8EB",
          "tolerance": 4,
          "min_support_ratio": 0.9,
          "max_row_offset_px": 1
        }
      },
      {
        "pixel": 830,
        "value": 23.5,
        "evidence": {
          "kind": "horizontal_reference_line",
          "role": "axis_tick",
          "x_range": [4, 30],
          "color": "#333333",
          "tolerance": 8,
          "min_support_ratio": 0.8,
          "max_row_offset_px": 1
        }
      }
    ]
  },
  "styles": [
    {
      "id": "cyan_filled",
      "kind": "filled",
      "colors": ["#00EBFF"],
      "tolerance": 12,
      "direction": "open_above_close",
      "geometry": {
        "min_body_width_px": 80,
        "max_body_width_px": 110,
        "max_wick_center_offset_px": 2
      }
    }
  ]
}
```

Never pass expected candle count, expected centers, dates, or OHLC values to the extractor.

## Geometry strategy

- Outline bodies: pair aligned top/bottom edges into one rectangle. Use compatible side evidence as a fallback when a label partially occludes one horizontal edge. The left and right borders are never separate candles.
- Filled bodies: find rows with repeated full body-width support. Do not use the longest center-column run as the body because a same-color wick can be contiguous with it.
- Wicks: follow narrow vertical evidence near the accepted body center. Hollow-body upper and lower wick segments are measured separately across the empty interior.
- Verified occluders: a separately configured color may bridge collinear wick topology only when the report retains `occluder_role: topology_only_not_numeric_fill`. It does not add colored pixels or values.

### Filled-body overlay bridging (`candidate-v2`)

Opt in with `bridge_filled_body_fragments: true` only for a filled style whose
indicator colors are explicitly listed as verified occluders and are separated
from every candle-color tolerance. Keep `occluder_role` equal to
`topology_only_not_numeric_fill`.

Merge only a directionally unique upper/lower fragment pair when the vertical
gap has verified occluder evidence, the fragments overlap horizontally, and
their union remains within the configured legal body width. A one-pixel
vertical evidence radius may account for an anti-aliased fringe; it must not
extend measured body endpoints. Preserve every accepted bridge in the report.

Keep conservative refusal when colors are not separable, pairing is ambiguous,
the union is too wide, the gap lacks verified evidence, or low resolution
prevents a unique inventory. Do not infer OHLC from the indicator line. With
bridging disabled or inapplicable, retain the `candidate-v1` behavior.

## Completeness and refusal

The report contains a **coverage ledger** with one entry for every accepted or unresolved candidate. Standard statuses are:

- `extracted`
- `ambiguous_body`
- `ambiguous_wick`
- `duplicate_candidate`
- `distractor_excluded`
- `not_extracted`

`numeric_output_authorized` is true only when every retained candidate is `extracted`, the source contract matches, calibration is valid, no duplicate or unresolved inventory remains, and every row satisfies:

```text
high >= max(open, close)
low  <= min(open, close)
```

When authorization is false, retain the report and overlay but emit no numeric data rows. Do not tune candidate inventory toward an external expected count.

## Evidence bundle

Every run writes a new, non-empty-directory-safe evidence bundle:

- `data.csv`: authorized OHLC and original-pixel geometry;
- `report.json`: source contract, algorithm version, configuration, calibration, candidates, coverage ledger, ambiguity, refusal reasons, and `numeric_output_authorized`;
- `overlay.png`: original-size accepted and ambiguous geometry for visual review.

Never overwrite an existing non-empty evidence directory. Open the overlay at original resolution and confirm that each body/wick annotation is supported by visible pixels.

## Benchmark workflow

When an independently prepared case directory contains `original.png`,
`manifest.json`, and evaluator-only `truth.csv`, run:

```powershell
python scripts/run_kline_benchmark.py `
  --case-dir path/to/case `
  --output-dir path/to/new-result
```

The runner creates separate outputs:

- `extraction/`: candidate CSV, report, and overlay;
- `validation/`: truth comparison CSV and evaluation JSON;
- `baseline/`: independent metrics from `scripts/legacy_digitize_kline.py`.

Report candle precision/recall/F1, one-to-one x matching, per-field OHLC MAE/RMSE/P95/max error, unmatched rows, invariant violations, unsafe false accepts, and reproducibility. `truth.csv`, annotated centers, dates, and OHLC values must become available only after extraction completes.

One tuning case cannot establish general support. Add deterministic synthetic,
real vector/rendered, and held-out real-raster cases split by renderer/source
image before considering promotion. Any case inspected or tuned before truth
evaluation remains regression evidence; use a fresh source for the next
held-out evaluation.

### Lightweight Charts synthetic tuning suite

The bundled generator creates 16 deterministic candlestick-chart fixtures with pinned `lightweight-charts`. They cover light/dark themes, Chinese/western palettes, filled/hollow bodies, doji and missing-wick geometry, density, moving-average lines, and Bollinger lines.

```powershell
python scripts/generate_lwc_benchmarks.py `
  --output-dir benchmarks/synthetic_lwc

python scripts/run_kline_benchmark_suite.py `
  --suite-dir benchmarks/synthetic_lwc `
  --output-dir benchmark-results/synthetic-lwc-v3 `
  --baseline-summary benchmark-results/synthetic-lwc-v2/suite-evaluation.json
```

Each case retains `original.png`, `truth.csv`, `manifest.json`, `render-spec.json`, renderer-coordinate metadata, and a README. The generator refuses a non-empty destination. The suite runner preserves every success, refusal, or error and writes `suite-evaluation.json` plus `suite-comparison.csv`.

Indicator lines are verified occluders with `topology_only_not_numeric_fill`; they may support bounded topology reconnection but never create or replace OHLC values. Truth, expected inventory, dates, and x centers remain evaluator-only.

Treat `synthetic-lwc-v3` as paired candidate evidence: require no regression on
cases without overlays, zero unsafe false accepts, and explicit retained
refusals for unresolved near-color, ambiguous, or low-resolution cases.

Every case is synthetic tuning evidence with `held_out: false`. Because all 16 cases share one renderer/template family, they do not establish cross-renderer or real-raster generalization and do not justify stable promotion.

## THU Digitizer integration path

For later integration, keep the compatibility route identifier `raster_kline_candidate` while presenting the feature as candlestick-chart digitization. Require explicit confirmations for source identity, plot bounds, price axis, style semantics, colors, width geometry, exclusions/occluders, and overlay review. Declare visible OHLC as recoverable and dates/volume/indicators/hidden records as non-recoverable.

Do not promote to stable until the THU Digitizer research-quality baseline is met across synthetic, vector/rendered, and held-out real-raster strata, existing stable tests show no regression, a fair WebPlotDigitizer comparison or precise `not_compared` reason is recorded, and the user explicitly approves promotion.
