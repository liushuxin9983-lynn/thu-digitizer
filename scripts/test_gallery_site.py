import csv
import json
import math
import unittest
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / "gallery"


class GallerySiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((GALLERY / "data" / "cases.json").read_text(encoding="utf-8"))
        cls.atlas = json.loads((GALLERY / "data" / "capabilities.json").read_text(encoding="utf-8"))
        cls.basics = json.loads((GALLERY / "data" / "basics.json").read_text(encoding="utf-8"))

    def test_static_entrypoints_exist(self):
        for relative in [
            "index.html",
            "home.css",
            "home.js",
            "capabilities.html",
            "styles.css",
            "app.js",
            "README.md",
            "ATTRIBUTION.md",
        ]:
            self.assertTrue((GALLERY / relative).is_file(), relative)

    def test_every_recreated_image_uses_the_original_canvas_dimensions(self):
        for sample in self.basics["samples"]:
            with self.subTest(sample=sample["id"]):
                with Image.open(GALLERY / sample["assets"]["original"]) as original:
                    with Image.open(GALLERY / sample["assets"]["recreated"]) as recreated:
                        self.assertEqual(recreated.size, original.size)

    def test_homepage_leads_with_image_extraction_only_chart_cases(self):
        samples = self.basics["samples"]
        self.assertEqual(
            [item["id"] for item in samples],
            [
                "line",
                "scatter",
                "nature-56055-fig3c",
                "dose-response",
                "bar",
                "bar-horizontal",
                "bar-stacked",
                "bar-percent-stacked",
                "histogram",
                "heatmap",
                "boxplot",
                "boxplot-horizontal",
                "forest",
                "nature-21043-fig6a",
                "nature-00142-fig3a",
                "nature-00142-fig4a",
                "nature-02571-fig1d",
                "nature-63786-fig1c",
                "nature-27341-fig1",
                "nature-70099-fig5e",
                "nature-37200-fig8e",
                "nature-31408-fig2d",
                "nature-06199-fig1",
                "nature-60895-fig4c",
            ],
        )
        self.assertEqual(sum(item["status"] == "validated_local_stable" for item in samples), 3)
        self.assertEqual(sum(item["status"] == "candidate" for item in samples), 7)
        self.assertEqual(next(item for item in samples if item["id"] == "forest")["status"], "visible_geometry_extracted")
        self.assertFalse(any(item["status"] == "source_mapped" for item in samples))

        html = (GALLERY / "index.html").read_text(encoding="utf-8")
        script = (GALLERY / "home.js").read_text(encoding="utf-8")
        self.assertIn("图表提取能力", html)
        self.assertIn("图形类型", html)
        self.assertNotIn('class="hero"', html)
        self.assertNotIn("FIGURE → DATA", html)
        self.assertNotIn('id="hero-title"', html)
        self.assertIn('href="capabilities.html"', html)
        self.assertIn('fetch("data/basics.json")', script)
        for label in ["原图", "提取覆盖", "复现"]:
            self.assertIn(label, script)

    def test_homepage_detail_has_scrollable_table_download_and_interactive_values(self):
        html = (GALLERY / "index.html").read_text(encoding="utf-8")
        css = (GALLERY / "home.css").read_text(encoding="utf-8")
        script = (GALLERY / "home.js").read_text(encoding="utf-8")

        for element_id in [
            "case-dialog",
            "detail-original-image",
            "detail-recreated-image",
            "original-source",
            "csv-download",
            "data-table-viewport",
            "interactive-chart",
            "chart-tooltip",
            "interactive-readout",
        ]:
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("拖动表格查看全部行列", html)
        self.assertIn("overflow: auto", css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", css)
        self.assertIn(".comparison-panel {\n  display: grid;\n  grid-column: 1 / -1;\n  grid-row: 1;", css)
        self.assertIn("height: clamp(320px, 38vw, 520px)", css)
        self.assertIn('class="interactive-chart comparison-interactive"', html)
        self.assertIn('id="detail-recreated-image"', html)
        self.assertIn('data-recreation-view="interactive"', html)
        self.assertIn('>交互式图</button>', html)
        self.assertNotIn('data-recreation-view="interactive">数据</button>', html)
        self.assertIn("function setRecreationView(view)", script)
        self.assertIn('setRecreationView("recreated")', script)
        self.assertIn("function displayType(sample)", script)
        self.assertIn('class="type-group"', script)
        self.assertIn("type-group-grid", css)
        self.assertIn("function updateOriginalSource(sample)", script)
        self.assertIn("function applyComparisonAlignment(sample)", script)
        self.assertIn("detailOriginalImage.naturalWidth", script)
        self.assertIn(".case-summary {\n  grid-column: 1 / -1;\n  grid-row: 2;", css)
        self.assertIn(".data-panel {\n  grid-column: 1 / -1;\n  grid-row: 3;", css)
        for implementation in [
            "parseCsv",
            "renderTable",
            "renderInteractiveChart",
            "data-tooltip",
            "download",
        ]:
            self.assertIn(implementation, script)

    def test_gallery_uses_audience_facing_status_labels(self):
        script = (GALLERY / "home.js").read_text(encoding="utf-8")
        self.assertIn("function publicStatusLabel(status)", script)
        self.assertIn("publicStatusLabel(sample.status)", script)
        self.assertNotIn("compactStatus(sample.statusLabel)", script)

    def test_paper_cases_have_brief_linked_original_source_metadata(self):
        paper_samples = [sample for sample in self.basics["samples"] if sample.get("articleUrl")]
        self.assertTrue(paper_samples)
        for sample in paper_samples:
            self.assertTrue(sample.get("journal"), sample["id"])
            self.assertTrue(sample.get("articleTitle"), sample["id"])
            self.assertTrue(sample.get("figure"), sample["id"])
            self.assertTrue(sample.get("figureUrl"), sample["id"])

    def test_style_backed_interactive_renderers_are_explicit(self):
        script = (GALLERY / "home.js").read_text(encoding="utf-8")
        style_samples = [sample for sample in self.basics["samples"] if sample.get("styleSpec")]
        self.assertEqual(
            {sample["id"] for sample in style_samples},
            {
                "dose-response",
                "bar",
                "heatmap",
                "boxplot",
                "nature-21043-fig6a",
                "nature-00142-fig3a",
                "nature-00142-fig4a",
                "nature-02571-fig1d",
                "nature-56055-fig3c",
                "nature-63786-fig1c",
                "nature-27341-fig1",
                "scatter",
                "nature-70099-fig5e",
                "nature-37200-fig8e",
                "nature-31408-fig2d",
                "nature-06199-fig1",
                "nature-60895-fig4c",
            },
        )
        renderers = {sample["styleSpec"]["renderer"] for sample in style_samples}
        self.assertEqual(
            renderers,
            {
                "paper-dose-response",
                "paper-grouped-bar",
                "paper-heatmap",
                "paper-boxplot",
                "paper-bubble-matrix",
                "paper-visible-bars",
                "paper-visible-upset",
                "paper-native-trace-line",
                "paper-native-geometry",
            },
        )
        for sample in style_samples:
            spec = sample["styleSpec"]
            with self.subTest(sample=sample["id"]):
                self.assertIn(
                    spec["fidelity"],
                    {
                        "evidence_backed_style_reconstruction",
                        "visible_geometry_candidate",
                    },
                )
                self.assertTrue(spec["label"])
                self.assertTrue(spec["note"])
                self.assertIn("canvas", spec)
                self.assertIn(spec["renderer"], script)
        self.assertIn("interactiveChart.dataset.styleMode", script)
        self.assertIn('data-style-mode="evidence-backed"', (GALLERY / "home.css").read_text(encoding="utf-8"))

    def test_raster_evidence_interaction_reuses_the_exact_recreation_canvas(self):
        script = (GALLERY / "home.js").read_text(encoding="utf-8")
        css = (GALLERY / "home.css").read_text(encoding="utf-8")
        raster_cases = [
            sample
            for sample in self.basics["samples"]
            if sample.get("styleSpec", {}).get("rasterEvidenceInteractive")
        ]
        self.assertTrue(raster_cases)
        self.assertIn("function renderRasterEvidenceInteractive", script)
        self.assertIn("href: assetUrl(sample.assets.recreated)", script)
        self.assertIn("comparison-stage > .interactive-chart.comparison-interactive", css)
        self.assertIn("min-height: 0", css)
        for sample in raster_cases:
            with self.subTest(sample=sample["id"]):
                spec = sample["styleSpec"]
                self.assertIn("canvas", spec)
                with (GALLERY / sample["assets"]["data"]).open(newline="", encoding="utf-8") as handle:
                    headers = next(csv.reader(handle))
                self.assertIn("pixel_x", headers)
                self.assertIn("pixel_y", headers)
                with Image.open(GALLERY / sample["assets"]["recreated"]) as recreation:
                    self.assertEqual(recreation.size, (spec["canvas"]["width"], spec["canvas"]["height"]))

    def test_basic_samples_have_complete_triptychs_and_evidence(self):
        for sample in self.basics["samples"]:
            with self.subTest(sample=sample["id"]):
                for key in ["original", "overlay", "recreated", "data", "report"]:
                    asset = GALLERY / sample["assets"][key]
                    self.assertTrue(asset.is_file(), f"{sample['id']}:{key}")
                    self.assertGreater(asset.stat().st_size, 0, f"{sample['id']}:{key}")
                for key in ["original", "overlay", "recreated"]:
                    with Image.open(GALLERY / sample["assets"][key]) as image:
                        self.assertGreater(image.width, 350)
                        self.assertGreater(image.height, 250)
                with (GALLERY / sample["assets"]["data"]).open(newline="", encoding="utf-8") as handle:
                    self.assertGreater(len(list(csv.DictReader(handle))), 0)
                report = json.loads((GALLERY / sample["assets"]["report"]).read_text(encoding="utf-8"))
                self.assertEqual(report["schema_version"], 1)

    def test_natcom_fig5e_scatter_case_is_data_and_geometry_consistent(self):
        sample = next(
            item for item in self.basics["samples"] if item["id"] == "nature-70099-fig5e"
        )
        with (GALLERY / sample["assets"]["data"]).open(
            newline="", encoding="utf-8"
        ) as handle:
            rows = list(csv.DictReader(handle))

        points = [row for row in rows if row["kind"] == "point"]
        lines = [row for row in rows if row["kind"] == "line"]
        self.assertEqual(
            Counter(row["series"] for row in points),
            Counter({"Aβ42/Aβ40 ratio": 17, "MoCA": 16, "p-Tau-181": 15}),
        )
        self.assertEqual(len(lines), 3)
        self.assertTrue(
            all(
                row["value_status"] == "refit_from_extracted_visible_points"
                for row in lines
            )
        )
        self.assertTrue(
            all(
                row["fit_intercept"]
                and row["fit_slope"]
                and row["residual_sd"]
                and row["recomputed_r"]
                and row["annotated_r"]
                and row["annotated_p"]
                for row in lines
            )
        )

        expected_correlations = {
            "Aβ42/Aβ40 ratio": -0.57,
            "MoCA": -0.34,
            "p-Tau-181": 0.12,
        }
        for series, expected in expected_correlations.items():
            series_rows = [row for row in points if row["series"] == series]
            x_values = [float(row["x"]) for row in series_rows]
            y_values = [float(row["y"]) for row in series_rows]
            x_mean = sum(x_values) / len(x_values)
            y_mean = sum(y_values) / len(y_values)
            numerator = sum(
                (x - x_mean) * (y - y_mean)
                for x, y in zip(x_values, y_values)
            )
            denominator = math.sqrt(
                sum((x - x_mean) ** 2 for x in x_values)
                * sum((y - y_mean) ** 2 for y in y_values)
            )
            self.assertAlmostEqual(numerator / denominator, expected, delta=0.01)

        visible_points_metric = next(
            metric for metric in sample["metrics"] if metric["label"] == "visible points"
        )
        self.assertEqual(visible_points_metric["value"], "48")
        self.assertFalse(sample["styleSpec"].get("rasterEvidenceInteractive", False))

        report = json.loads(
            (GALLERY / sample["assets"]["report"]).read_text(encoding="utf-8")
        )
        self.assertEqual(report["visible_point_count"], 48)
        self.assertEqual(report["visible_points_by_panel"], [17, 16, 15])
        self.assertEqual(report["fit_representation"], "OLS refit from extracted visible points")
        self.assertEqual(report["ribbon_representation"], "fitted line ± residual SD")

    def test_bubble_matrix_uses_only_image_extracted_geometry(self):
        sample = next(item for item in self.basics["samples"] if item["id"] == "nature-21043-fig6a")
        root = GALLERY / sample["assets"]["data"]
        with root.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 208)
        self.assertEqual(len({(row["row"], row["column"]) for row in rows}), 208)
        self.assertEqual(sum(row["visible_marker"] == "true" for row in rows), 207)
        self.assertEqual(sum(row["visible_mark"] == "dot" for row in rows), 124)
        self.assertEqual(sum(row["visible_mark"] == "circle" for row in rows), 83)
        self.assertFalse({"mean", "p_value", "source_size_proxy", "source_status"}.intersection(rows[0]))
        for row in rows:
            if row["visible_marker"] == "true":
                self.assertTrue(row["visible_color"].startswith("#"))
                self.assertGreater(float(row["visible_radius_px"]), 0)
                self.assertIn(row["visible_geometry_status"], {"raster_detected_marker"})
        report = json.loads((GALLERY / sample["assets"]["report"]).read_text(encoding="utf-8"))
        self.assertEqual(report["coverage"]["categorical_grid_slots"], 208)
        self.assertEqual(report["coverage"]["visible_raster_markers"], 207)
        self.assertEqual(report["coverage"]["unmatched_grid_slots"], 1)
        self.assertEqual(report["pixel_extraction"]["unassigned_components"], 0)

    def test_vertical_boxplot_is_the_real_nature_medicine_case(self):
        sample = next(item for item in self.basics["samples"] if item["id"] == "boxplot")
        self.assertEqual(sample["status"], "candidate")
        self.assertEqual(
            sample["articleUrl"],
            "https://www.nature.com/articles/s41591-026-04303-y",
        )
        report = json.loads((GALLERY / sample["assets"]["report"]).read_text(encoding="utf-8"))
        self.assertEqual(report["case_id"], "nature-protaide-boxplot")
        self.assertEqual(report["stable_baseline"]["status"], "low_confidence")
        self.assertEqual(report["candidate_extraction"]["box_groups_extracted"], 20)
        self.assertEqual(report["candidate_extraction"]["box_groups_visible"], 20)
        self.assertEqual(report["candidate_extraction"]["visible_outliers_extracted"], 9)
        self.assertEqual(report["candidate_extraction"]["raster_coincident_medians"], 1)
        with (GALLERY / sample["assets"]["data"]).open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 20)
        self.assertEqual({row["panel"] for row in rows}, {"BCA", "AUC"})
        self.assertEqual({row["series"] for row in rows}, {"Retrain", "Finetune"})


    def test_grouped_bar_is_real_raster_extraction_with_vector_validation(self):
        sample = next(item for item in self.basics["samples"] if item["id"] == "bar")
        self.assertEqual(sample["status"], "candidate")
        self.assertEqual(
            sample["articleUrl"],
            "https://www.nature.com/articles/s41467-026-68864-9",
        )
        report_path = GALLERY / sample["assets"]["report"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["case_id"], "nature-oatman-grouped-bar")
        extraction = report["candidate_extraction"]
        self.assertEqual(extraction["status"], "candidate")
        self.assertEqual(extraction["summary"]["extracted_mark_count"], 32)
        self.assertEqual(extraction["summary"]["missing_mark_count"], 0)
        self.assertEqual(extraction["summary"]["ambiguous_mark_count"], 0)
        self.assertEqual(extraction["summary"]["excluded_component_count"], 2)
        validation = report["vector_validation"]
        self.assertEqual(validation["status"], "validated_real_vector_geometry")
        self.assertEqual(validation["matched_bars"], 32)
        self.assertLess(validation["mae"], validation["raster_value_per_pixel"])
        case_root = report_path.parent
        for name in ["vector-reference.json", "vector-validation.csv", "vector-validation.png"]:
            self.assertTrue((case_root / name).is_file(), name)
            self.assertGreater((case_root / name).stat().st_size, 0, name)
        with (GALLERY / sample["assets"]["data"]).open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 32)
        self.assertEqual({row["series"] for row in rows}, {"CER", "TCX"})

    def test_dose_response_is_pdf_vector_extraction_with_separate_validation(self):
        sample = next(item for item in self.basics["samples"] if item["id"] == "dose-response")
        self.assertEqual(sample["status"], "candidate")
        self.assertEqual(
            sample["articleUrl"],
            "https://www.nature.com/articles/s41467-026-71361-8",
        )
        report_path = GALLERY / sample["assets"]["report"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["case_id"], "nature-kahlous-dose-response")
        extraction = report["candidate_extraction"]
        self.assertEqual(extraction["route"], "verified_vector_pdf_geometry")
        self.assertEqual(extraction["summary"]["visible_marker_count"], 21)
        self.assertEqual(extraction["summary"]["main_marker_count"], 18)
        self.assertEqual(extraction["summary"]["vehicle_marker_count"], 3)
        self.assertEqual(extraction["summary"]["visible_error_bar_count"], 14)
        self.assertEqual(extraction["summary"]["traced_curve_count"], 3)
        validation = report["source_validation"]
        self.assertEqual(validation["source_matched_markers"], 18)
        self.assertEqual(validation["source_uncovered_vehicle_markers"], 3)
        self.assertEqual(validation["sem_occluded_by_marker"], 4)
        self.assertLess(validation["marker_mae"], 0.05)
        self.assertLess(validation["marker_max_absolute_error"], 0.1)
        self.assertLess(validation["visible_error_endpoint_mae"], 0.06)
        case_root = report_path.parent
        for name in [
            "source-article.pdf",
            "source-data.xlsx",
            "curves.csv",
            "source-validation.csv",
            "source-validation.png",
            "vector-inspection.json",
        ]:
            self.assertTrue((case_root / name).is_file(), name)
            self.assertGreater((case_root / name).stat().st_size, 0, name)
        with (GALLERY / sample["assets"]["data"]).open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 21)
        self.assertEqual({row["series"] for row in rows}, {"ADR", "NA", "DA"})
        self.assertFalse({"source_mean", "source_sem", "source_status", "marker_error"}.intersection(rows[0]))
        self.assertTrue(all(row["status"] == "vector_marker_extracted" for row in rows))

    def test_public_primary_data_never_contains_author_source_fields(self):
        banned_tokens = ("source", "author", "official")
        for sample in self.basics["samples"]:
            with (GALLERY / sample["assets"]["data"]).open(newline="", encoding="utf-8") as handle:
                headers = next(csv.reader(handle))
            with self.subTest(sample=sample["id"]):
                self.assertFalse(
                    [header for header in headers if any(token in header.lower() for token in banned_tokens)],
                    headers,
                )

    def test_heatmap_is_calibrated_and_validated_against_suppdata_8(self):
        sample = next(item for item in self.basics["samples"] if item["id"] == "heatmap")
        self.assertEqual(sample["status"], "candidate")
        self.assertEqual(
            sample["articleUrl"],
            "https://www.nature.com/articles/s41591-026-04303-y",
        )
        report_path = GALLERY / sample["assets"]["report"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["case_id"], "nature-protaide-heatmap")
        self.assertEqual(report["candidate_extraction"]["status"], "candidate")
        self.assertEqual(report["candidate_extraction"]["cell_count"], 672)
        validation = report["source_validation"]
        self.assertEqual(validation["matched_cells"], 672)
        self.assertEqual(validation["numeric_cells"], 578)
        self.assertEqual(validation["endpoint_censored_cells"], 94)
        self.assertLess(validation["numeric_mae"], 0.005)
        self.assertEqual(validation["significance"]["true_positive"], 456)
        self.assertEqual(validation["significance"]["false_positive"], 0)
        self.assertEqual(validation["significance"]["false_negative"], 1)
        case_root = report_path.parent
        for name in ["source-data.xlsx", "source-validation.csv", "source-validation.png"]:
            self.assertTrue((case_root / name).is_file(), name)
            self.assertGreater((case_root / name).stat().st_size, 0, name)
        with (GALLERY / sample["assets"]["data"]).open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 672)
        self.assertEqual({row["value_status"] for row in rows}, {"numeric", "clipped_high", "clipped_low"})

    def test_homepage_paper_cases_keep_article_provenance(self):
        self.assertEqual(len(self.basics["paperCases"]), 2)
        for case in self.basics["paperCases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(case["journal"], "Nature Communications")
                self.assertTrue(case["articleUrl"].startswith("https://www.nature.com/articles/"))
                for key in ["original", "overlay", "recreated", "data", "report"]:
                    self.assertTrue((GALLERY / case["assets"][key]).is_file())

    def test_manifest_has_three_complementary_cases(self):
        cases = self.manifest["cases"]
        self.assertEqual(len(cases), 3)
        self.assertEqual(
            {case["verification"] for case in cases},
            {
                "official_source_data_mapped",
                "visible_geometry_extracted",
                "partial_visible_geometry",
            },
        )

    def test_case_assets_and_external_metadata(self):
        for case in self.manifest["cases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(case["license"], "CC BY 4.0")
                self.assertTrue(case["articleUrl"].startswith("https://www.nature.com/articles/"))
                self.assertTrue(case["figureUrl"].endswith("/figures/2"))
                for key in ["original", "overlay", "recreated", "data", "report", "sourceData"]:
                    asset = GALLERY / case["assets"][key]
                    self.assertTrue(asset.is_file(), f"{case['id']}:{key}")
                    self.assertGreater(asset.stat().st_size, 0, f"{case['id']}:{key}")

                for key in ["original", "overlay", "recreated"]:
                    with Image.open(GALLERY / case["assets"][key]) as image:
                        self.assertGreater(image.width, 200)
                        self.assertGreater(image.height, 150)

    def test_reports_match_manifest_claims(self):
        for case in self.manifest["cases"]:
            report = json.loads((GALLERY / case["assets"]["report"]).read_text(encoding="utf-8"))
            with self.subTest(case=case["id"]):
                self.assertEqual(report["case_id"], case["id"])
                self.assertEqual(report["status"], case["verification"])
                self.assertIn("limitations", report)
                self.assertGreater(len(report["limitations"]), 0)

    def test_download_csvs_are_nonempty(self):
        for case in self.manifest["cases"]:
            with (GALLERY / case["assets"]["data"]).open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            with self.subTest(case=case["id"]):
                self.assertGreater(len(rows), 0)

    def test_borneo_axis_scope_is_explicit(self):
        case = next(item for item in self.manifest["cases"] if item["id"] == "nature-borneo-edge")
        report = json.loads((GALLERY / case["assets"]["report"]).read_text(encoding="utf-8"))
        with (GALLERY / case["assets"]["data"]).open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(report["source_rows"], 71)
        self.assertEqual(report["panel_a_visible_rows"], 50)
        self.assertEqual(report["panel_a_out_of_range_rows"], 21)
        self.assertEqual(sum(row["panel_a_visible"] == "True" for row in rows), 50)

    def test_html_exposes_auditable_views_and_claim_warning(self):
        html = (GALLERY / "capabilities.html").read_text(encoding="utf-8")
        script = (GALLERY / "app.js").read_text(encoding="utf-8")
        for label in ["论文原图", "提取覆盖层", "数据复现图"]:
            self.assertIn(label, script)
        self.assertIn("WebPlotDigitizer：尚未进行同条件比较", html)
        self.assertIn("不照搬 R Graph Gallery 的七类", html)
        self.assertIn('fetch("data/capabilities.json")', script)
        self.assertIn('fetch("data/cases.json")', script)
        for view in ["original", "overlay", "recreated"]:
            self.assertIn(f"{view}:", script)

    def test_digitization_taxonomy_is_not_r_graph_gallery_seven_groups(self):
        self.assertEqual(self.atlas["taxonomySource"]["model"], "digitization-layered-taxonomy")
        self.assertEqual(self.atlas["counts"]["groups"], 13)
        self.assertEqual(self.atlas["counts"]["types"], 77)
        self.assertGreaterEqual(self.atlas["counts"]["oaRepresentatives"], 50)
        self.assertEqual(len(self.atlas["groups"]), 13)
        self.assertNotEqual(
            {group["id"] for group in self.atlas["groups"]},
            {"distribution", "correlation", "ranking", "part", "evolution", "map", "flow"},
        )

    def test_wpd_calibration_families_and_thu_extensions_are_explicit(self):
        routes = self.atlas["calibrationFamilies"]
        wpd = {item["id"] for item in routes if item["origin"] == "WebPlotDigitizer"}
        extensions = {item["id"] for item in routes if item["origin"] == "thu-digitizer extension"}
        self.assertEqual(
            wpd,
            {"xy", "bar", "polar", "ternary", "map_scale", "image_pixel", "circular_recorder"},
        )
        self.assertEqual(extensions, {"structure", "semantic_router"})

    def test_every_group_and_route_has_capabilities(self):
        capabilities = self.atlas["capabilities"]
        group_ids = {group["id"] for group in self.atlas["groups"]}
        route_ids = {route["id"] for route in self.atlas["calibrationFamilies"]}
        self.assertEqual({item["group"] for item in capabilities}, group_ids)
        self.assertEqual({item["calibrationFamily"] for item in capabilities}, route_ids)
        for group_id in group_ids:
            self.assertGreater(sum(item["group"] == group_id for item in capabilities), 0)

    def test_capability_statuses_and_references_are_valid(self):
        engine_statuses = set(self.atlas["statusDefinitions"]["engine"])
        demo_statuses = set(self.atlas["statusDefinitions"]["demo"])
        cases = {case["id"]: case for case in self.atlas["referenceCases"]}
        self.assertEqual(len(cases), self.atlas["counts"]["referenceFigures"])

        for item in self.atlas["capabilities"]:
            with self.subTest(capability=item["id"]):
                self.assertIn(item["engineStatus"], engine_statuses)
                self.assertIn(item["demoStatus"], demo_statuses)
                self.assertTrue(item["recoverableRepresentation"])
                self.assertTrue(item["nonRecoverable"])
                if item["caseId"]:
                    self.assertIn(item["caseId"], cases)
                    self.assertIsNotNone(item["thumbnail"])
                    self.assertTrue((GALLERY / item["thumbnail"]).is_file())
                else:
                    self.assertEqual(item["demoStatus"], "no_case")

    def test_reference_figures_have_oa_provenance_and_reports(self):
        for case in self.atlas["referenceCases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(case["license"], "CC BY 4.0")
                self.assertTrue(case["articleUrl"].startswith("https://www.nature.com/articles/"))
                self.assertTrue(case["figureUrl"].startswith(case["articleUrl"] + "/figures/"))
                self.assertEqual(len(case["originalSha256"]), 64)
                original = GALLERY / case["original"]
                report_path = GALLERY / case["report"]
                self.assertTrue(original.is_file())
                self.assertTrue(report_path.is_file())
                with Image.open(original) as image:
                    self.assertGreater(image.width, 500)
                    self.assertGreater(image.height, 200)
                report = json.loads(report_path.read_text(encoding="utf-8"))
                if case["evidenceStatus"] == "oa_reference":
                    self.assertEqual(report["status"], "oa_reference_identified")
                    self.assertIn("no numeric values", report["scope"])

    def test_challenge_queue_assets_exist(self):
        self.assertGreater(len(self.manifest["challengeQueue"]), 0)
        for item in self.manifest["challengeQueue"]:
            self.assertTrue((GALLERY / item["image"]).is_file())
            self.assertEqual(item["status"], "challenge_queued")


if __name__ == "__main__":
    unittest.main()
