# THU Digitizer

Research-first chart digitization skill for recovering and validating numeric data from raster charts, PDF figures, and official source-data files.

## Development

- Skill instructions: `SKILL.md`
- Extractors and regression tests: `scripts/`
- Research baseline and workflow references: `references/`
- SciFigureHub taxonomy/challenge protocol: `references/scifigurehub-benchmark.md`
- Unified preflight and FigureSpec contract: `references/unified-routing.md`
- Unified route registry and CLI: `scripts/extractor_registry.py`, `scripts/figure_spec.py`, `scripts/thu_digitizer.py`
- Candidate assisted bar extractor: `scripts/candidate_digitize_bar_chart.py`
- Nature Communications grouped-bar raster/vector regression: `scripts/build_natcom_grouped_bar_case.py`
- Candidate calibrated heatmap extractor: `scripts/candidate_digitize_heatmap.py`
- Candidate paired outline-boxplot extractor: `scripts/candidate_digitize_outline_boxplot.py`
- Candidate vector-PDF dose-response extractor: `scripts/candidate_digitize_dose_response_pdf.py`
- Nature Communications dose-response PDF/source-data regression: `scripts/build_natcom_dose_response_case.py`
- OA figure capability atlas: `gallery/`（首页 12 类原图卡片、案例详情、可拖动 CSV 表格、精度证据、交互数据视图，以及 13 个提取类别和 77 种图表类型的能力索引）
- Run the test suite from `scripts/`:

  ```powershell
  python -m unittest discover -p 'test_*.py' -v
  ```

Preview the gallery from the repository root:

```powershell
python -m http.server 8793 --bind 127.0.0.1 --directory gallery
```

Inspect a new input before running a family-specific extractor:

```powershell
python scripts\thu_digitizer.py inspect `
  --input figure.png --chart-type histogram `
  --output-report preflight-report.json `
  --output-spec figure-spec.json
```

The route and full-image panel remain proposals until their FigureSpec verification fields are completed. Unknown and incompatible chart types are refused instead of being forced through an XY extractor.

For local Codex discovery, keep the clone in a stable location and create a
junction from the Codex skills directory to the clone. On Windows PowerShell:

```powershell
New-Item -ItemType Junction `
  -Path "$env:USERPROFILE\.codex\skills\thu-digitizer" `
  -Target "<path-to-your-clone>"
```

Large or disposable benchmark runs belong under `D:\Scratch`, not in this repository. Keep only small, reproducible fixtures and manifests under version control.

The assisted bar, paired outline-boxplot, calibrated heatmap, and vector-PDF dose-response routes are intentionally marked `candidate`. Their current synthetic and real-figure regressions document the supported geometry and refusal behavior, but they must not be promoted until the research baseline's held-out real-raster, WebPlotDigitizer comparison, and approval gates are complete.
