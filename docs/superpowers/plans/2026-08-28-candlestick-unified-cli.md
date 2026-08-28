# Candlestick Unified CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make candlestick extraction a registered THU Digitizer candidate route that can be preflighted and executed through `scripts/thu_digitizer.py` to produce a source-locked CSV, JSON report, and overlay.

**Architecture:** Migrate the existing detector into `scripts/candlestick_extractor.py` unchanged in its evidence and refusal logic, then add a narrow adapter which converts one verified candlestick FigureSpec panel into the detector configuration. The unified CLI owns readiness checks, route selection, and structured refusal output; the detector owns original-pixel geometry and OHLC measurement.

**Tech Stack:** Python 3.10+, standard library `argparse`/`json`/`unittest`, NumPy, Pillow, existing THU Digitizer FigureSpec and extractor registry.

## Global Constraints

- Register `candlestick` as candidate route id `raster_candlestick_candidate`; do not describe it as stable.
- Only raster inputs and a verified linear price axis are supported; do not silently rasterize PDFs or apply a log-price calibration.
- Preserve original-raster pixels, SHA-256, width, height, coverage ledger, refusal reasons, and original-size overlay.
- Emit numeric OHLC rows only when `numeric_output_authorized` is true; never provide expected count, dates, truth values, or evaluator-only data to the detector.
- A non-empty evidence directory remains an error and is never overwritten.
- Remove the duplicate `candlestick-digitizer/` package after its code and relevant tests are migrated.

---

## Target file structure

- `scripts/candlestick_extractor.py` — migrated pure detector API and evidence writer.
- `scripts/candidate_digitize_candlestick.py` — FigureSpec-to-detector adapter and structured refusal writer.
- `scripts/extractor_registry.py` — candlestick route metadata and aliases.
- `scripts/figure_spec.py` — validation of the candlestick route configuration.
- `scripts/thu_digitizer.py` — `extract` subcommand and dispatch to the adapter.
- `scripts/test_candlestick_extractor.py` — migrated detector safety and artifact tests.
- `scripts/test_thu_digitizer_router.py` — route/preflight coverage for candlesticks.
- `scripts/test_figure_spec.py` — candlestick FigureSpec contract coverage.
- `scripts/test_candlestick_unified_cli.py` — public `extract` command end-to-end coverage.
- `benchmarks/candlestick/` — migrated synthetic and real-raster fixtures, separated from evaluator truth.
- `SKILL.md` and `references/unified-routing.md` — user-facing candidate capability and one-command workflow.

### Task 1: Migrate the detector as a reusable main-repository module

**Files:**
- Create: `scripts/candlestick_extractor.py`
- Create: `scripts/test_candlestick_extractor.py`
- Delete: `candlestick-digitizer/scripts/kline_extractor.py`
- Delete: `candlestick-digitizer/scripts/digitize_kline.py`

**Interfaces:**
- Consumes: `Path | str` input image and a source-locked detector configuration.
- Produces: `extract_candlesticks(image_path, extraction_config) -> tuple[ExtractionResult, dict]` and `write_extraction_artifacts(image_path, result, metadata, output_dir) -> Path`.
- Raises: `ExtractionRefused(reason_code, details)` for hard-contract failures.

- [ ] **Step 1: Write failing import and artifact tests**

```python
from pathlib import Path
import tempfile
import unittest

from candlestick_extractor import ExtractionRefused, extract_candlesticks, write_extraction_artifacts


class CandlestickExtractorContractTests(unittest.TestCase):
    def test_mismatched_source_contract_is_refused(self):
        with self.assertRaisesRegex(ExtractionRefused, "source_contract_mismatch"):
            extract_candlesticks(Path("tests/fixtures/candlestick.png"), {
                "source_contract": {"sha256": "0" * 64, "width": 1, "height": 1},
                "plot_bounds": [0, 0, 1, 1], "price_axis": {"scale": "linear", "anchors": []}, "styles": [],
            })

    def test_evidence_writer_refuses_nonempty_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "existing.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                write_extraction_artifacts(Path("tests/fixtures/candlestick.png"), None, {}, output)
```

- [ ] **Step 2: Run the focused test to verify the missing module fails**

Run: `python -m unittest scripts.test_candlestick_extractor -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'candlestick_extractor'`.

- [ ] **Step 3: Move the detector without changing its evidence semantics**

```python
# scripts/candlestick_extractor.py
# Rename the existing implementation to _extract_candlesticks_impl,
# then expose the candlestick terminology.
def extract_candlesticks(image_path: Path | str, extraction_config: dict) -> tuple[ExtractionResult, dict]:
    return _extract_candlesticks_impl(image_path, extraction_config)
```

Use `git mv candlestick-digitizer/scripts/kline_extractor.py scripts/candlestick_extractor.py`, then rename the original implementation to `_extract_candlesticks_impl` so the public function calls it exactly once. Preserve `ExtractionRefused`, the source contract, price-anchor evidence verification, coverage ledger, and `write_extraction_artifacts` byte-for-byte apart from import/module names.

- [ ] **Step 4: Port detector regression tests and fixtures**

Copy the existing source tests that assert source-contract mismatch, anchor-evidence refusal, body/wick ambiguity, OHLC invariants, and non-empty output-directory refusal into `scripts/test_candlestick_extractor.py`. Place the required images/configurations under `scripts/fixtures/candlestick/`; retain fixture hashes and do not add any truth CSV to the extractor configuration.

- [ ] **Step 5: Run migrated detector tests**

Run: `python -m unittest scripts.test_candlestick_extractor -v`

Expected: PASS; every refusal test asserts a machine-readable `reason_code` and every successful fixture writes `data.csv`, `report.json`, and `overlay.png`.

- [ ] **Step 6: Commit detector migration**

```powershell
git add scripts/candlestick_extractor.py scripts/test_candlestick_extractor.py scripts/fixtures/candlestick
git rm candlestick-digitizer/scripts/kline_extractor.py candlestick-digitizer/scripts/digitize_kline.py
git commit -m "refactor: move candlestick detector into unified scripts"
```

### Task 2: Register and validate the candlestick FigureSpec route

**Files:**
- Modify: `scripts/extractor_registry.py`
- Modify: `scripts/figure_spec.py`
- Modify: `scripts/thu_digitizer.py`
- Modify: `scripts/test_thu_digitizer_router.py`
- Modify: `scripts/test_figure_spec.py`

**Interfaces:**
- Consumes: `chart_type="candlestick"` and a single raster panel.
- Produces: a FigureSpec panel with route id `raster_candlestick_candidate`, coordinate model `categorical_value`, axes `category` and `price`, and `route_config`.

- [ ] **Step 1: Write failing routing and FigureSpec tests**

```python
def test_candlestick_preflight_registers_candidate_route(self):
    report, spec = build_preflight(self.image, chart_type="candlestick")
    panel = spec["panels"][0]
    self.assertEqual(report["route_selection"]["primary"]["route_id"], "raster_candlestick_candidate")
    self.assertEqual(panel["coordinate_model"], "categorical_value")
    self.assertIn("price_axis", panel["required_confirmations"])
    self.assertFalse(report["safety"]["numeric_extraction_authorized"])

def test_candlestick_ready_spec_requires_linear_verified_price_axis_and_styles(self):
    spec = candlestick_ready_spec()
    spec["panels"][0]["route_config"]["price_axis"]["scale"] = "log10"
    errors = validate_figure_spec(spec)
    self.assertTrue(any("candlestick price_axis.scale" in error for error in errors))
```

- [ ] **Step 2: Run tests to prove the route is absent**

Run: `python -m unittest scripts.test_thu_digitizer_router scripts.test_figure_spec -v`

Expected: FAIL because `candlestick` selects `unknown_refuse` and `route_config` is not validated.

- [ ] **Step 3: Add route metadata and a route-config validator**

```python
# scripts/extractor_registry.py
RouteDescriptor(
    "raster_candlestick_candidate", "Visible raster candlestick OHLC",
    ("candlestick",), ("raster",), ("categorical_value",),
    ("candle_body", "wick", "price_reference_line"), "candidate",
    "scripts/candidate_digitize_candlestick.py",
    ("panel_roi", "plot_bounds", "price_axis", "style_semantics", "candle_geometry", "overlay_review"),
    "Visible separable candle-body and wick geometry calibrated to a verified linear price axis.",
    "Dates, volume, indicators, hidden records, log-price axes, fused candles, and unresolved wicks.", True,
)
```

Implement `_validate_candlestick_route_config(panel, errors, path)` in `figure_spec.py`. Require `route_config.price_axis.scale == "linear"`, exactly two numeric/evidenced anchors, at least one style with `id`, `kind` in `{filled, outline}`, `colors`, numeric non-negative `tolerance`, and direction in `{open_above_close, close_above_open}`. Require finite positive body-width bounds and non-negative wick-centre tolerance. Call the validator only when `panel.route.route_id == "raster_candlestick_candidate"`.

- [ ] **Step 4: Generate the right preflight template**

```python
# scripts/thu_digitizer.py::_axis_templates
if coordinate_model == "categorical_value":
    return [
        {"axis_id": "category", "orientation": "category", "scale": "categorical", "verification": "not_applicable", "anchors": []},
        {"axis_id": "price", "orientation": "y", "scale": "linear", "verification": "missing", "anchors": []},
    ]
```

When building a candlestick panel, add a `route_config` template with `price_axis`, empty `styles`, `duplicate_distance_px`, and optional exclusions/occluders marked missing; do not invent colours, anchors, or geometry.

- [ ] **Step 5: Run route and schema tests**

Run: `python -m unittest scripts.test_thu_digitizer_router scripts.test_figure_spec -v`

Expected: PASS; candidate route is selected, incomplete templates stay unready, and invalid price/style configurations are rejected.

- [ ] **Step 6: Commit route contract**

```powershell
git add scripts/extractor_registry.py scripts/figure_spec.py scripts/thu_digitizer.py scripts/test_thu_digitizer_router.py scripts/test_figure_spec.py
git commit -m "feat: register candlestick figure route"
```

### Task 3: Add the unified extraction adapter and CLI command

**Files:**
- Create: `scripts/candidate_digitize_candlestick.py`
- Modify: `scripts/thu_digitizer.py`
- Create: `scripts/test_candlestick_unified_cli.py`

**Interfaces:**
- Consumes: `extract --spec PATH --output-dir PATH`.
- Produces: exit code 0 plus `data.csv`, `report.json`, `overlay.png` when authorized; exit code 2 plus `report.json` only for a validated but refused candidate.

- [ ] **Step 1: Write failing public CLI tests**

```python
def run_extract(spec: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "thu_digitizer.py"), "extract", "--spec", str(spec), "--output-dir", str(output)],
        text=True, capture_output=True,
    )

def test_extract_writes_standard_authorized_evidence_bundle(self):
    completed = run_extract(READY_SYNTHETIC_SPEC, self.output)
    self.assertEqual(completed.returncode, 0, completed.stderr)
    self.assertTrue((self.output / "data.csv").exists())
    self.assertTrue((self.output / "report.json").exists())
    self.assertTrue((self.output / "overlay.png").exists())

def test_extract_refuses_unverified_spec_without_numeric_csv(self):
    completed = run_extract(UNVERIFIED_SPEC, self.output)
    self.assertEqual(completed.returncode, 2)
    self.assertTrue((self.output / "report.json").exists())
    self.assertFalse((self.output / "data.csv").exists())
```

- [ ] **Step 2: Run the end-to-end test to verify `extract` is unavailable**

Run: `python -m unittest scripts.test_candlestick_unified_cli -v`

Expected: FAIL with argparse reporting `extract` as an invalid command.

- [ ] **Step 3: Implement one-panel candlestick adapter**

```python
def extraction_config_from_spec(spec: dict) -> tuple[Path, dict]:
    panel = spec["panels"][0]
    if panel["route"]["route_id"] != "raster_candlestick_candidate":
        raise ValueError("unsupported_extract_route")
    route_config = panel["route_config"]
    return Path(spec["source"]["input_file"]), {
        "source_contract": {key: spec["source"][key] for key in ("sha256", "width", "height")},
        "plot_bounds": panel["plot_bounds"],
        "price_axis": route_config["price_axis"],
        "styles": route_config["styles"],
        "duplicate_distance_px": route_config.get("duplicate_distance_px", 15),
    }
```

`run_candlestick_extraction(spec, output_dir)` must check `figure_spec_readiness(spec)` before detector invocation. For a readiness failure, create only `report.json` with `numeric_output_authorized: false`, `refusal_reasons: ["figure_spec_not_ready"]`, readiness details, source identity, and selected route. For a detector refusal, preserve the detector reason code and write the same structured report without creating numeric rows.

- [ ] **Step 4: Wire `extract` into the main parser**

```python
extract = subparsers.add_parser("extract", help="Run one verified registered extractor")
extract.add_argument("--spec", required=True, type=Path)
extract.add_argument("--output-dir", required=True, type=Path)
```

Load the spec with `read_figure_spec`; reject multiple panels with `multiple_panel_extract_not_implemented`; dispatch only the candlestick route; return exit code 2 for candidate refusal and a nonzero configuration error for unknown/unimplemented route ids.

- [ ] **Step 5: Add hash-mismatch regression case and run CLI tests**

```python
def test_extract_preserves_source_contract_mismatch_as_refusal(self):
    completed = run_extract(HASH_MISMATCH_SPEC, self.output)
    self.assertEqual(completed.returncode, 2)
    report = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
    self.assertIn("source_contract_mismatch", report["refusal_reasons"])
    self.assertFalse((self.output / "data.csv").exists())
```

Run: `python -m unittest scripts.test_candlestick_unified_cli -v`

Expected: PASS; all successful evidence is original-size and all refusals avoid numeric CSV output.

- [ ] **Step 6: Commit the adapter and CLI**

```powershell
git add scripts/candidate_digitize_candlestick.py scripts/thu_digitizer.py scripts/test_candlestick_unified_cli.py
git commit -m "feat: run candlestick extraction through unified cli"
```

### Task 4: Migrate benchmarks and enforce regression evidence

**Files:**
- Create: `benchmarks/candlestick/`
- Create: `scripts/run_candlestick_benchmark.py`
- Create: `scripts/generate_candlestick_benchmarks.py`
- Create: `scripts/synthetic_candlestick_cases.py`
- Create: `scripts/test_candlestick_benchmark.py`
- Delete: `candlestick-digitizer/scripts/run_kline_benchmark.py`
- Delete: `candlestick-digitizer/scripts/run_kline_benchmark_suite.py`
- Delete: `candlestick-digitizer/scripts/evaluate_kline.py`
- Delete: `candlestick-digitizer/scripts/legacy_digitize_kline.py`

**Interfaces:**
- Consumes: benchmark manifest whose extractor section contains no truth or expected inventory.
- Produces: separate `extraction/`, `validation/`, and `baseline/` directories; only the evaluator reads `truth.csv`.

- [ ] **Step 1: Write benchmark-isolation test**

```python
def test_benchmark_never_passes_truth_to_unified_extractor(self):
    manifest = load_manifest(CASE_DIR / "manifest.json")
    spec = figure_spec_from_manifest(manifest)
    serialized = json.dumps(spec)
    self.assertNotIn("truth.csv", serialized)
    self.assertNotIn("expected_count", serialized)
    self.assertNotIn("x_center_px", serialized)
```

- [ ] **Step 2: Run it to prove the unified runner does not exist**

Run: `python -m unittest scripts.test_candlestick_benchmark -v`

Expected: FAIL with missing `run_candlestick_benchmark` module.

- [ ] **Step 3: Port fixtures and route the extraction phase through the public CLI adapter**

Copy the existing `kline_sample_001`, Snowball regression, and `synthetic_lwc` fixtures into `benchmarks/candlestick/`, retaining their manifests and source identity. Move the synthetic generator and case builder to `scripts/generate_candlestick_benchmarks.py` and `scripts/synthetic_candlestick_cases.py`; retain their renderer metadata and truth isolation. Rename only public text from K-line to candlestick. The runner must build a verified FigureSpec from the extraction-only manifest, call `run_candlestick_extraction`, and invoke the evaluator only after extraction finishes.

- [ ] **Step 4: Run focused benchmark regression tests**

Run: `python -m unittest scripts.test_candlestick_benchmark -v`

Expected: PASS; the accepted tuning fixture retains its existing metrics and the low-resolution/ambiguous cases preserve refusals rather than unsafe numeric acceptance.

- [ ] **Step 5: Run the full suite**

Run: `python -m unittest discover scripts -p "test_*.py" -v`

Expected: PASS; all pre-existing THU Digitizer routes retain their behavior.

- [ ] **Step 6: Commit migrated evaluation evidence**

```powershell
git add benchmarks/candlestick scripts/run_candlestick_benchmark.py scripts/generate_candlestick_benchmarks.py scripts/synthetic_candlestick_cases.py scripts/test_candlestick_benchmark.py
git rm candlestick-digitizer/scripts/run_kline_benchmark.py candlestick-digitizer/scripts/run_kline_benchmark_suite.py candlestick-digitizer/scripts/evaluate_kline.py candlestick-digitizer/scripts/legacy_digitize_kline.py
git commit -m "test: migrate candlestick benchmark coverage"
```

### Task 5: Remove the standalone package and document the unified workflow

**Files:**
- Modify: `SKILL.md`
- Modify: `references/unified-routing.md`
- Modify: `README.md`
- Delete: `candlestick-digitizer/SKILL.md`
- Delete: `candlestick-digitizer/agents/openai.yaml`
- Delete: `candlestick-digitizer/scripts/generate_lwc_benchmarks.py`
- Delete: `candlestick-digitizer/scripts/synthetic_kline_cases.py`
- Delete: `candlestick-digitizer/scripts/package.json`
- Delete: `candlestick-digitizer/scripts/package-lock.json`
- Delete: `candlestick-digitizer/scripts/render_lwc_case.mjs`

**Interfaces:**
- Consumes: a completed, verified candlestick FigureSpec.
- Produces: documented command `python scripts/thu_digitizer.py extract --spec candlestick-spec.json --output-dir evidence`.

- [ ] **Step 1: Write documentation assertions before changing docs**

```python
def test_root_skill_documents_candlestick_candidate_and_unified_command(self):
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    self.assertIn("candlestick", text)
    self.assertIn("raster_candlestick_candidate", text)
    self.assertIn("thu_digitizer.py extract", text)
    self.assertIn("numeric_output_authorized", text)
    self.assertIn("Dates, volume, indicators", text)
```

- [ ] **Step 2: Run documentation test to verify it fails**

Run: `python -m unittest scripts.test_candlestick_unified_cli.CandlestickDocumentationTests -v`

Expected: FAIL because root documentation does not yet describe the unified candlestick route.

- [ ] **Step 3: Update user-facing documentation**

Add a short candidate section to `SKILL.md` and `README.md` showing the two-command path: `inspect --chart-type candlestick`, manual verification of the generated spec, then `extract --spec candlestick-spec.json --output-dir evidence`. Update `references/unified-routing.md` to list the raster-only fallback and never authorize a PDF directly. State the explicit visible-OHLC limits and the refusal/overlay review requirement.

- [ ] **Step 4: Delete the duplicate package after verifying its contents are migrated**

Before deletion, compare every tracked `candlestick-digitizer/` file against its replacement or documented removal. Remove the directory only after detector, tests, benchmarks, generator dependencies, and documentation references have migrated or been deliberately retired.

- [ ] **Step 5: Run final verification**

Run: `python -m unittest discover scripts -p "test_*.py" -v`

Expected: PASS with no remaining import or documentation link to `candlestick-digitizer/`.

Run: `git diff --check; git status --short`

Expected: no whitespace errors; only intended migration changes are staged.

- [ ] **Step 6: Commit documentation and cleanup**

```powershell
git add SKILL.md README.md references/unified-routing.md scripts/test_candlestick_unified_cli.py
git rm -r candlestick-digitizer
git commit -m "docs: integrate candlestick digitizer workflow"
```

## Plan self-review

- Spec coverage: Tasks 1–5 cover detector migration, registered routing, validated FigureSpec configuration, one-command extraction, refusal behavior, evidence artifacts, benchmarks, documentation, and standalone-package removal.
- Placeholder scan: no unfinished markers or unspecified test steps remain.
- Type consistency: `raster_candlestick_candidate`, `extract_candlesticks`, `run_candlestick_extraction`, `route_config`, and `data.csv`/`report.json`/`overlay.png` use the same names throughout.
