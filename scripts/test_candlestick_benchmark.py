"""Regression tests for the unified candlestick benchmark runner."""

from __future__ import annotations

import json
import hashlib
import importlib
import tempfile
import unittest
from pathlib import Path

try:
    from run_candlestick_benchmark import (
        figure_spec_from_manifest,
        load_manifest,
        run_benchmark,
    )
    from figure_spec import assert_valid_figure_spec
except ImportError:  # package-style unittest invocation
    from .run_candlestick_benchmark import (
        figure_spec_from_manifest,
        load_manifest,
        run_benchmark,
    )
    from .figure_spec import assert_valid_figure_spec


ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "benchmarks" / "candlestick" / "kline_sample_001"


class BenchmarkIsolationTests(unittest.TestCase):
    def test_benchmark_never_passes_truth_to_unified_extractor(self):
        manifest = load_manifest(CASE_DIR / "manifest.json")
        spec = figure_spec_from_manifest(manifest)
        serialized = json.dumps(spec)
        self.assertNotIn("truth.csv", serialized)
        self.assertNotIn("expected_count", serialized)
        self.assertNotIn("x_center_px", serialized)

    def test_manifest_builds_a_verified_candlestick_figure_spec(self):
        spec = figure_spec_from_manifest(load_manifest(CASE_DIR / "manifest.json"))
        assert_valid_figure_spec(spec)
        self.assertEqual(spec["status"], "ready_for_assisted_extraction")
        self.assertEqual(
            spec["panels"][0]["route"]["route_id"],
            "raster_candlestick_candidate",
        )


class MigratedFixtureTests(unittest.TestCase):
    def test_migrated_sources_retain_manifest_identity(self):
        roots = [
            CASE_DIR,
            ROOT
            / "benchmarks"
            / "candlestick"
            / "snowball_calibration_regression_001",
        ]
        suite = ROOT / "benchmarks" / "candlestick" / "synthetic_lwc"
        roots.extend(
            suite / item["path"]
            for item in json.loads((suite / "suite.json").read_text(encoding="utf-8"))[
                "cases"
            ]
        )
        self.assertEqual(len(roots), 18)
        for case_dir in roots:
            manifest = load_manifest(case_dir / "manifest.json")
            digest = hashlib.sha256(
                (case_dir / manifest["image"]["file"]).read_bytes()
            ).hexdigest().upper()
            self.assertEqual(digest, manifest["image"]["sha256"], case_dir.name)

    def test_synthetic_case_builder_retains_the_four_by_four_matrix(self):
        cases = importlib.import_module(
            "scripts.synthetic_candlestick_cases"
        ).case_definitions()
        self.assertEqual(len(cases), 16)
        self.assertEqual(len({case["case_id"] for case in cases}), 16)
        family_counts = {
            family: sum(case["family"] == family for case in cases)
            for family in ("base", "geometry", "ma", "bollinger")
        }
        self.assertEqual(
            family_counts,
            {"base": 4, "geometry": 4, "ma": 4, "bollinger": 4},
        )

    def test_migrated_generator_validates_the_retained_suite(self):
        generator = importlib.import_module(
            "scripts.generate_candlestick_benchmarks"
        )
        self.assertTrue((generator.RENDERER_ROOT / "render_lwc_case.mjs").is_file())
        self.assertTrue(
            (
                generator.RENDERER_ROOT
                / "node_modules"
                / "lightweight-charts"
                / "dist"
                / "lightweight-charts.standalone.production.js"
            ).is_file()
        )
        generator.validate_suite(
            ROOT / "benchmarks" / "candlestick" / "synthetic_lwc"
        )


class BenchmarkRegressionTests(unittest.TestCase):
    def run_case(self, case_dir: Path) -> tuple[Path, dict]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = run_benchmark(case_dir, Path(temporary.name) / "run")
        evaluation = json.loads(
            (output / "validation" / "evaluation.json").read_text(encoding="utf-8")
        )
        return output, evaluation

    def test_accepted_tuning_fixture_retains_metrics_and_separate_evidence(self):
        output, evaluation = self.run_case(CASE_DIR)
        self.assertEqual(
            {path.name for path in output.iterdir()},
            {"extraction", "validation", "baseline"},
        )
        self.assertTrue(evaluation["numeric_output_authorized"])
        self.assertEqual(evaluation["matched_count"], 11)
        self.assertEqual(evaluation["precision"], 1.0)
        self.assertEqual(evaluation["recall"], 1.0)
        self.assertEqual(evaluation["f1"], 1.0)
        self.assertLessEqual(
            max(value["mae"] for value in evaluation["fields"].values()),
            0.01,
        )
        self.assertLessEqual(
            max(
                value["max_absolute_error"]
                for value in evaluation["fields"].values()
            ),
            0.03,
        )
        self.assertEqual(evaluation["unsafe_false_accept_count"], 0)
        baseline = json.loads(
            (output / "baseline" / "evaluation.json").read_text(encoding="utf-8")
        )
        self.assertEqual(baseline["implementation"], "retired_candlestick_baseline")

    def test_snowball_calibration_regression_retains_accepted_gates(self):
        case = (
            ROOT
            / "benchmarks"
            / "candlestick"
            / "snowball_calibration_regression_001"
        )
        _, evaluation = self.run_case(case)
        self.assertTrue(evaluation["numeric_output_authorized"])
        self.assertEqual(evaluation["matched_count"], 24)
        self.assertEqual(evaluation["precision"], 1.0)
        self.assertEqual(evaluation["recall"], 1.0)
        self.assertEqual(evaluation["f1"], 1.0)
        self.assertLessEqual(
            max(value["mae"] for value in evaluation["fields"].values()),
            1.0,
        )
        self.assertLessEqual(
            max(
                value["max_absolute_error"]
                for value in evaluation["fields"].values()
            ),
            2.0,
        )
        self.assertTrue(evaluation["all_required_gates_pass"])
        self.assertEqual(evaluation["failed_gates"], [])

    def test_low_resolution_and_ambiguous_cases_preserve_safe_refusals(self):
        suite = ROOT / "benchmarks" / "candlestick" / "synthetic_lwc"
        case_ids = [
            "synthetic_lwc_012_near_color_ma",
            "synthetic_lwc_016_lowres_combined",
        ]
        for case_id in case_ids:
            with self.subTest(case_id=case_id):
                output, evaluation = self.run_case(suite / case_id)
                self.assertFalse(evaluation["numeric_output_authorized"])
                self.assertEqual(
                    {path.name for path in (output / "extraction").iterdir()},
                    {"report.json"},
                )
                self.assertEqual(evaluation["detected_count"], 0)
                self.assertEqual(evaluation["unsafe_false_accept_count"], 0)
                self.assertTrue(evaluation["refusal_reasons"])


if __name__ == "__main__":
    unittest.main()
