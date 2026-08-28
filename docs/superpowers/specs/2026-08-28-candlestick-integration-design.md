# Candlestick digitizer integration design

## Goal

Integrate the existing candlestick-chart detector into THU Digitizer as a
single, evidence-bound candidate route. A user must be able to preflight,
complete a verified FigureSpec, and invoke the unified CLI to produce the
standard evidence bundle without using a separate skill or CLI.

## Scope and maturity

The registered chart type is `candlestick` and the route id is
`raster_candlestick_candidate`. It remains a candidate extractor. It recovers
only visibly supported Open, High, Low, and Close values from a raster chart
with a verified linear price axis. Dates, volume, indicators, hidden exchange
records, unresolved candles, and non-linear price axes remain non-recoverable.

## Architecture

Move the detector implementation from the standalone `candlestick-digitizer/`
directory into the main repository's `scripts/` package, with the detector
available as a reusable Python API. Remove the duplicate standalone skill and
CLI entry point after the unified adapter is verified.

Register `candlestick` in `scripts/extractor_registry.py` with raster-only,
linear-price, body-and-wick mark grammar metadata, required confirmations, and
candidate maturity. Extend the FigureSpec contract with a candlestick-specific
route configuration containing:

- verified `plot_bounds` in original-raster pixels;
- a verified linear `price` axis with at least two evidenced anchors;
- one or more visual styles, each with colours, tolerance, body kind, and
  open/close direction semantics;
- body-width bounds, wick-centre tolerance, exclusions, and optional verified
  topology-only occluders.

## Unified CLI flow

`python scripts/thu_digitizer.py inspect --chart-type candlestick ...` writes
a normal FigureSpec template and never authorizes numeric output.

`python scripts/thu_digitizer.py extract --spec candlestick-spec.json
--output-dir evidence` validates the shared FigureSpec, requires every route
confirmation to be verified, converts the verified route configuration to the
detector configuration, and invokes the candlestick adapter. The adapter writes
the standard `data.csv`, `report.json`, and original-size `overlay.png`.

If the spec is incomplete, its source contract does not match the input, or
the detector has unresolved bodies or wicks, extraction returns a structured
refusal report and does not write numeric data rows. The extractor must never
receive benchmark truth, expected candle counts, dates, or expected OHLC values.

## Migration and compatibility

Existing synthetic and real-raster fixtures, evaluator code, and regression
tests move into the main repository's test and benchmark layout. The existing
route identifier and all evidence semantics are preserved where possible; only
the user-facing entry point becomes unified. No compatibility wrapper is kept
for the uploaded standalone directory, because that would preserve two
competing configuration and evidence contracts.

## Verification

Add unit tests for route registration, FigureSpec validation, and route-config
translation. Add end-to-end tests through `thu_digitizer.py extract` for a
successful synthetic fixture, an incomplete/unverified FigureSpec refusal, and
a source SHA-256 mismatch refusal. Run the migrated candlestick suite alongside
the existing THU Digitizer test suite, preserving the candidate status unless
the repository's research-quality promotion requirements are independently met.

## Documentation

Update the root `SKILL.md`, unified-routing reference, route listing, and
capability/limits text. Documentation must state that candlestick extraction is
a candidate, requires an explicitly verified linear price axis and style
semantics, and returns visible OHLC only when the evidence bundle authorizes it.
