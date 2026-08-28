# Final Whole-Branch Review Fix Report

Date: 2026-08-28

## Outcome

All final review findings were addressed. The candlestick route now has one validated geometry authority, generic categorical routes retain their original value-axis contract, source identity is strict, public source failures are report-only refusals, and the naming migration is complete.

## Candlestick geometry and overlay controls

- `figure_spec.py` owns the complete allow-list and validation rules for every detector geometry control.
- Ready specs declare geometry under `route_config.geometry.styles`, keyed exactly by unique configured style ids.
- Style-local geometry is rejected, so a ready spec cannot carry a second divergent geometry source.
- Unknown geometry fields, invalid control types/ranges, missing required width/wick controls, duplicate style ids, and geometry/style-key mismatches are rejected.
- `candidate_digitize_candlestick.py` constructs each detector style from the validated route-level entry; it does not read geometry from the public style object.
- Exclusion and occluder dictionaries accept only `verification` and `regions`. Because the detector has no region implementation, any non-empty regions or other controls are rejected before detector invocation.
- Benchmark FigureSpec generation now migrates the detector's existing per-style settings into the authoritative route geometry map without changing detector behavior.

Regression coverage proves route geometry reaches both filled and outline detector inputs exactly, style-local/unknown geometry refuses, style keys must match, and a non-empty exclusion refuses before a mocked detector can run.

## Route-specific axes

The generic `categorical_value` template once again emits `category` plus `value`. Only `raster_candlestick_candidate` requests `category` plus `price`. Router regression coverage includes bar, filled box, paired outline box, and candlestick routes.

## Source contract and public refusals

FigureSpec source validation now requires:

- `input_file`: non-empty string;
- `resampling_applied`: the boolean value `false`, explicitly present;
- `sha256`: exactly 64 hexadecimal characters.

The public candlestick extraction path normalizes missing, unreadable/directory, and non-image inputs into `source_unavailable`, `source_unreadable`, and `source_not_image` refusal reports. Each regression asserts that `report.json` is the only artifact in the output directory.

## Naming cleanup

The temporary compatibility alias was removed, the evidence report algorithm name is now `raster_candlestick_candidate`, and old internal/public detector identifiers no longer occur in the working tree.

## Verification evidence

Focused contract and regression suite:

```text
python -m unittest scripts.test_figure_spec scripts.test_candlestick_unified_cli scripts.test_thu_digitizer_router scripts.test_candlestick_benchmark scripts.test_candlestick_extractor -v
Ran 68 tests in 6.254s
OK
```

Full suite:

```text
python -W ignore -m unittest discover -s scripts -p 'test_*.py'
205 tests discovered
Exit code: 0
```

Repository checks:

```text
git diff --check
Exit code: 0

rg -n <retired alias and detector identifiers> .
No matches
```

The full suite's normal non-suppressed run also exited zero; its only diagnostics were pre-existing Pillow deprecation warnings for the `mode` parameter in unrelated bar, boxplot, and histogram image helpers.
