# Unified preflight routing and FigureSpec

## Purpose

Use `scripts/thu_digitizer.py` before a new extraction. It separates four decisions that were previously repeated across case builders:

1. input composition (raster, vector PDF, or mixed PDF);
2. chart-type hint and whether it has been verified;
3. coordinate model and calibration requirements;
4. registered extractor maturity, limits, and required confirmations.

The preflight output never authorizes numeric extraction. It writes a valid configuration template whose unverified fields remain explicitly marked `missing`, `proposed`, or `user_provided`.

## Commands

List the registry:

```powershell
python scripts\thu_digitizer.py routes
```

Inspect a raster:

```powershell
python scripts\thu_digitizer.py inspect `
  --input chart.png `
  --chart-type histogram `
  --output-report preflight-report.json `
  --output-spec figure-spec.json
```

Inspect one PDF page and supply a panel proposal:

```powershell
python scripts\thu_digitizer.py inspect `
  --input article.pdf --page 7 `
  --chart-type dose_response `
  --panel-bounds 55,178,235,310 `
  --output-report preflight-report.json `
  --output-spec figure-spec.json
```

Validate a manually completed spec without running extraction:

```powershell
python scripts\thu_digitizer.py validate-spec --spec figure-spec.json
```

## FigureSpec contract

`scripts/figure_spec.py` validates a shared structure:

- source hash, media kind, coordinate space, dimensions, and PDF page;
- one or more panel bounds with a separate verification status;
- chart type and coordinate model without treating either as verified by default;
- typed axes with calibration scale, anchors, and verification status;
- series placeholders and visible mark grammars;
- selected route, maturity, implementation path, and required confirmations;
- recoverable and explicitly non-recoverable representations;
- the evidence bundle required after extraction.

The schema distinguishes:

- `log10`: raw positive values displayed on a logarithmic axis;
- `displayed_log10`: a linear coordinate whose printed values are already logarithms, such as `log [ligand], M` from -10 to -2.

This distinction prevents a correct negative displayed-log calibration from being rejected or, conversely, a raw logarithmic axis from being calibrated linearly.

## Route-selection discipline

The machine-readable registry lives in `scripts/extractor_registry.py`. Registry presence is not a support claim.

- A clean raster histogram can select the stable histogram implementation, but still requires verified plot bounds, axes, and colour.
- A vector dose-response PDF can select its dedicated candidate, but still requires verified page, panel, axes, marker shapes, colours, and legend exclusions.
- A generic vector PDF selects inspection-assisted routing first and retains an eligible raster fallback when available.
- A vector PDF enters generic vector-assisted recovery only when that chart family is declared compatible. Otherwise it either requires an explicit page-to-raster step or returns a chart-specific refusal.
- A raster dose-response image currently refuses the PDF-only extractor.
- Unknown or non-Cartesian types never fall through to a generic XY extractor.
- Case-only or unimplemented coordinate families return `not_automated` or `unsupported`.

## What this improvement does not claim

This layer does not yet classify charts automatically, detect panels reliably, read ticks through OCR, or execute every extractor from one command. It provides a common, testable boundary between proposals and verified numeric work. Extraction adapters may be added route by route without changing the evidence or refusal contract.
