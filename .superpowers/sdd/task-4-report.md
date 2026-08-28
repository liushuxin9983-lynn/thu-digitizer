# Task 4 report: candlestick benchmark migration

## Implementation

- Migrated `kline_sample_001`, `snowball_calibration_regression_001`, and the
  16-case `synthetic_lwc` suite into `benchmarks/candlestick/` without changing
  source rasters, manifest source hashes, renderer metadata, or evaluator truth.
- Added `scripts/run_candlestick_benchmark.py`. It constructs and validates a
  ready candlestick FigureSpec from extraction-only manifest fields, calls
  `run_candlestick_extraction`, and does not open `truth.csv` until the adapter
  has returned. It writes separate `extraction/`, `validation/`, and `baseline/`
  directories.
- Kept refusal evidence report-only: the ambiguous near-colour case and the
  low-resolution combined case produce only `extraction/report.json`, zero
  detected rows in validation, and zero unsafe false accepts.
- Ported the deterministic case matrix and generator as
  `scripts/synthetic_candlestick_cases.py` and
  `scripts/generate_candlestick_benchmarks.py`. The generator resolves the
  repository-root renderer/dependencies first and the adjacent main checkout
  as a worktree fallback; a fresh 16-case generation completed successfully.
- Replaced the executable legacy baseline with an explicit retired-baseline
  record. Historical Snowball first-run evidence remains embedded when present,
  without rerunning deleted legacy extraction code.
- Deleted the four superseded benchmark/evaluator/legacy scripts requested in
  the brief.

## RED evidence

Initial isolation test:

```text
python -m unittest scripts.test_candlestick_benchmark -v
```

Failed with `ModuleNotFoundError: No module named 'run_candlestick_benchmark'`.

Snowball gate regression:

```text
python -m unittest scripts.test_candlestick_benchmark.BenchmarkRegressionTests.test_snowball_calibration_regression_retains_accepted_gates -v
```

Failed with `KeyError: 'all_required_gates_pass'` before gate evidence was
implemented.

Synthetic migration:

```text
python -m unittest scripts.test_candlestick_benchmark.MigratedFixtureTests.test_synthetic_case_builder_retains_the_four_by_four_matrix scripts.test_candlestick_benchmark.MigratedFixtureTests.test_migrated_generator_validates_the_retained_suite -v
```

Failed because both migrated modules were absent. A later renderer-dependency
regression failed because the old package-local `node_modules` path did not
exist; this caught the generator's first worktree migration attempt.

## GREEN evidence

Focused benchmark suite:

```text
python -m unittest scripts.test_candlestick_benchmark -v
```

Result: 8 tests passed in 0.700 seconds.

Relevant candlestick integration suite:

```text
python -m unittest scripts.test_candlestick_benchmark scripts.test_candlestick_unified_cli scripts.test_candlestick_extractor scripts.test_figure_spec scripts.test_thu_digitizer_router -v
```

Result: 55 tests passed in 2.273 seconds.

Fresh generator smoke test:

```text
python scripts/generate_candlestick_benchmarks.py --output-dir <fresh-temp>/suite
```

Result: completed all 16 cases and printed `SUITE_OUTPUT=.../suite`. All 97
case artifacts matched the retained suite byte-for-byte; only the suite README
line-ending bytes differed.

Static checks:

```text
python -m compileall -q scripts/run_candlestick_benchmark.py scripts/generate_candlestick_benchmarks.py scripts/synthetic_candlestick_cases.py scripts/test_candlestick_benchmark.py
git diff --check
```

Result: both exited 0 with no diagnostics.

## Full-suite evidence

Command:

```text
python -m unittest discover scripts -p "test_*.py" -v
```

Result: 192 tests ran; 187 passed, 1 skipped, and 4 errored for pre-existing
workspace/environment reasons outside this task:

- three China Mining isogram tests require absent ignored evidence under
  `outputs/china-mining-gakedaban-dt-300m/visible-contour-extraction-v2-full-legend/`;
- one gallery test calls Pillow `Image.get_flattened_data`, which is unavailable
  in the installed Pillow 11.3.0.

All new benchmark tests and all candlestick/unified-route tests passed within
that full run. No claim is made that the repository-wide suite is fully green.

## Files

- Created `benchmarks/candlestick/kline_sample_001/`.
- Created `benchmarks/candlestick/snowball_calibration_regression_001/`.
- Created `benchmarks/candlestick/synthetic_lwc/`.
- Created `scripts/run_candlestick_benchmark.py`.
- Created `scripts/generate_candlestick_benchmarks.py`.
- Created `scripts/synthetic_candlestick_cases.py`.
- Created `scripts/test_candlestick_benchmark.py`.
- Deleted `candlestick-digitizer/scripts/run_kline_benchmark.py`.
- Deleted `candlestick-digitizer/scripts/run_kline_benchmark_suite.py`.
- Deleted `candlestick-digitizer/scripts/evaluate_kline.py`.
- Deleted `candlestick-digitizer/scripts/legacy_digitize_kline.py`.
- Created `.superpowers/sdd/task-4-report.md`.

## Self-review

- `figure_spec_from_manifest` serializes no `truth.csv`, `expected_count`, or
  `x_center_px`, and the candidate adapter remains the only extraction entry.
- The evaluator's truth read is localized to `_evaluate_after_extraction`,
  after `run_candlestick_extraction` returns.
- All 18 migrated source rasters are rehashed in tests against their retained
  manifest SHA-256 identities.
- Accepted K-line-ID and corrected Snowball tuning cases retain full coverage,
  perfect precision/recall/F1, accepted error gates, and zero unsafe accepts.
- Ambiguous/low-resolution cases retain conservative report-only refusals.
- The runner refuses nonempty evidence directories through the unified adapter
  and never mixes extraction, validation, or retired-baseline artifacts.

## Concerns

- The complete repository suite remains blocked by three absent ignored gallery
  evidence files and one Pillow-version API mismatch, as detailed above.
- The renderer and npm dependency files remain repository-root concerns for the
  package-removal task. The migrated generator prefers that final root layout
  and uses the adjacent main checkout only while this integration worktree does
  not yet contain those root files.

## Code-review remediation

This section supersedes the original full-suite and renderer concerns above.

### Findings and fixes

1. The migrated generator searched `ROOT.parent.parent` and therefore depended
   on the adjacent main checkout. Added tracked repository-root
   `render_lwc_case.mjs`, `package.json`, and `package-lock.json`; the generator
   now uses only its own repository root. A clean dependency install is
   `npm ci --ignore-scripts` from that root.
2. The stress-case reporting gate returned `bool(threshold)`, which proved only
   that the manifest contained a truthy declaration. Each validation report now
   carries concrete `coverage_evidence` recording attempt, validation, outcome,
   and refusal reasons. The gate fails when that evidence is absent or
   inconsistent and verifies report-only refusals against the recorded reasons.
3. The four full-suite errors were reproducible but feasible compatibility
   defects rather than candlestick regressions:
   - three China Mining tests addressed an ignored intermediate `outputs/`
     directory even though the same evidence is published and tracked under
     `gallery/assets/cases/china-mining-gakedaban-dt-300m/`; the tests now use
     those tracked artifacts;
   - one gallery test used Pillow 12's `get_flattened_data` while this runtime
     has Pillow 11.3.0; it now selects `get_flattened_data` when available and
     otherwise uses `getdata`, without changing the pixel assertion.

### Review RED evidence

```text
python -m unittest scripts.test_candlestick_benchmark.MigratedFixtureTests.test_migrated_generator_validates_the_retained_suite scripts.test_candlestick_benchmark.BenchmarkRegressionTests.test_low_resolution_and_ambiguous_cases_preserve_safe_refusals scripts.test_candlestick_benchmark.BenchmarkRegressionTests.test_stress_reporting_gate_requires_concrete_coverage_evidence -v
```

Result before fixes: generator root assertion failed because it resolved to the
adjacent checkout; both refusal cases lacked `coverage_evidence`; removing
coverage evidence did not fail the stress reporting gate.

The exact full discovery command consistently produced three
`FileNotFoundError` failures under ignored `outputs/` and one `AttributeError`
for `Image.get_flattened_data` before the compatibility changes.

### Review GREEN evidence

Focused suite:

```text
python -m unittest scripts.test_candlestick_benchmark -v
```

Result: 9 tests passed in 0.708 seconds.

Clean-clone-style generator check:

```text
npm ci --ignore-scripts
python scripts/generate_candlestick_benchmarks.py --output-dir <fresh-temp>/suite
```

Result: npm installed the four locked packages with zero vulnerabilities; the
generator completed all 16 cases using only tracked repository-root renderer
and dependency declarations.

Full discovery:

```text
python -m unittest discover scripts -p "test_*.py" -v
```

Result: 193 tests ran in 14.098 seconds; 192 passed, 1 was intentionally
skipped, and there were no failures or errors.

### Review files

- Created `render_lwc_case.mjs`.
- Created `package.json`.
- Created `package-lock.json`.
- Modified `scripts/generate_candlestick_benchmarks.py`.
- Modified `scripts/run_candlestick_benchmark.py`.
- Modified `scripts/test_candlestick_benchmark.py`.
- Modified `scripts/test_china_mining_isogram_extraction.py`.
- Modified `scripts/test_gallery_site.py`.

### Review self-review

- No generator code searches outside the repository root.
- `node_modules` was used only for the clean-install verification and removed
  afterward; it is not committed.
- The stress gate is negative-tested by deleting `coverage_evidence` and
  requiring the gate to fail.
- Refusal coverage stores no numeric OHLC values; it contains only attempt,
  validation, authorization status, and refusal reason codes.
- Full-suite fixes point tests at already tracked equivalent evidence and add a
  two-version Pillow iteration fallback; no gallery assets or extraction logic
  were changed.
