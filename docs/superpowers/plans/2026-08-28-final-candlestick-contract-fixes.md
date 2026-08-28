# Final Candlestick Contract Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the final whole-branch review findings by making the candlestick detector contract authoritative, preserving generic categorical routes, hardening source validation/refusal behavior, and completing the candlestick naming migration.

**Architecture:** FigureSpec remains the public validation boundary. The candlestick adapter will derive every detector style geometry field from the single verified route-level geometry contract and reject unsupported non-empty region controls before detector invocation. Generic preflight axes remain category/value, while the candlestick route alone uses category/price. Public extraction converts invalid or unavailable sources into a report-only refusal directory.

**Tech Stack:** Python 3, unittest, Pillow, pathlib, git.

## Global Constraints

- A ready candlestick spec must have one authoritative verified geometry/exclusions/occluders contract.
- Existing bar, box, and outline categorical routes must retain category/value axes.
- FigureSpec source requires a non-empty string input_file, explicit false resampling_applied, and exactly 64 hexadecimal SHA-256 characters.
- Public extraction failures must leak no empty or partial numeric artifacts.
- Public and internal identifiers use candlestick terminology consistently.

---

### Task 1: Authoritative candlestick detector contract

**Files:**
- Modify: `scripts/figure_spec.py`
- Modify: `scripts/candidate_digitize_candlestick.py`
- Test: `scripts/test_figure_spec.py`
- Test: `scripts/test_candlestick_unified_cli.py`

**Interfaces:**
- Consumes: validated `panel.route_config.geometry`, `.exclusions`, and `.occluders`.
- Produces: detector `styles[*].geometry` derived solely from the verified route geometry; structured refusal before detector invocation for unsupported non-empty region controls.

- [ ] Add focused tests proving divergent style geometry is rejected/ignored, route geometry reaches every detector style exactly, and non-empty unsupported regions refuse before invocation.
- [ ] Run the focused tests and confirm they fail for the reviewed gaps.
- [ ] Implement the minimal validator/adapter mapping and refusal behavior.
- [ ] Re-run the focused tests and confirm they pass.

### Task 2: Route-specific categorical axes

**Files:**
- Modify: `scripts/thu_digitizer.py`
- Test: `scripts/test_thu_digitizer_router.py`

**Interfaces:**
- Consumes: selected route id and generic `categorical_value` coordinate model.
- Produces: category/price axes only for `raster_candlestick_candidate`; category/value axes for existing generic categorical routes.

- [ ] Add regression tests for candlestick, bar, box, and outline preflight axis ids.
- [ ] Run them and confirm the generic-route test fails.
- [ ] Scope the price-axis specialization to the candlestick route.
- [ ] Re-run the router tests.

### Task 3: Source contract and report-only public refusals

**Files:**
- Modify: `scripts/figure_spec.py`
- Modify: `scripts/candidate_digitize_candlestick.py`
- Test: `scripts/test_figure_spec.py`
- Test: `scripts/test_candlestick_unified_cli.py`

**Interfaces:**
- Consumes: public FigureSpec dictionaries and source image paths.
- Produces: validation errors for malformed source identity; one `report.json` and no other artifacts for missing, unreadable, or non-image sources.

- [ ] Add tests for missing/empty/non-string input_file, absent/true/non-bool resampling_applied, non-hex digest, and unavailable/invalid image extraction.
- [ ] Run them and confirm expected failures.
- [ ] Harden source validation and normalize public extraction exceptions into structured refusal reason codes.
- [ ] Re-run focused tests and inspect refusal directories.

### Task 4: Naming cleanup, full verification, report, and commit

**Files:**
- Modify: candlestick implementation/tests/docs containing legacy k-line identifiers.
- Create: `.superpowers/sdd/final-fix-report.md`

**Interfaces:**
- Produces: candlestick-only naming, verified focused/full test evidence, and one final commit.

- [ ] Search the repository and remove obsolete aliases/legacy identifiers without changing unrelated historical benchmark labels.
- [ ] Run focused candlestick/FigureSpec/router tests.
- [ ] Run the full suite and confirm zero failures.
- [ ] Re-read each requirement against the diff and write the final report with commands/results.
- [ ] Commit all final-review fixes and the report.
