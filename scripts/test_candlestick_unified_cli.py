from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
IMAGE = SCRIPTS / "fixtures" / "candlestick" / "single_filled_candle.png"


def run_extract(spec: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "thu_digitizer.py"),
            "extract",
            "--spec",
            str(spec),
            "--output-dir",
            str(output),
        ],
        text=True,
        capture_output=True,
    )


def ready_spec() -> dict:
    source_sha256 = hashlib.sha256(IMAGE.read_bytes()).hexdigest().upper()
    anchors = [
        {"pixel": 10, "value": 100.0},
        {"pixel": 90, "value": 0.0},
    ]
    return {
        "schema_version": 1,
        "status": "ready_for_assisted_extraction",
        "source": {
            "input_file": str(IMAGE.resolve()),
            "sha256": source_sha256,
            "media_kind": "raster",
            "coordinate_space": "pixel",
            "measurement_space": "original_raster_pixels",
            "resampling_applied": False,
            "width": 100,
            "height": 100,
        },
        "panels": [
            {
                "panel_id": "panel-1",
                "bounds": [0, 0, 100, 100],
                "bounds_verification": "verified",
                "plot_bounds": [10, 10, 90, 90],
                "plot_bounds_verification": "verified",
                "chart_type": "candlestick",
                "coordinate_model": "categorical_value",
                "axes": [
                    {
                        "axis_id": "category",
                        "scale": "categorical",
                        "verification": "not_applicable",
                        "anchors": [],
                    },
                    {
                        "axis_id": "price",
                        "scale": "linear",
                        "verification": "verified",
                        "anchors": copy.deepcopy(anchors),
                    },
                ],
                "mark_grammars": ["candle_body", "wick"],
                "route": {
                    "route_id": "raster_candlestick_candidate",
                    "maturity": "candidate",
                },
                "required_confirmations": [
                    "panel_roi",
                    "plot_bounds",
                    "price_axis",
                    "style_semantics",
                    "candle_geometry",
                    "overlay_review",
                ],
                "confirmations": {
                    "panel_roi": "verified",
                    "plot_bounds": "verified",
                    "price_axis": "verified",
                    "style_semantics": "verified",
                    "candle_geometry": "verified",
                    "overlay_review": "verified",
                },
                "route_config": {
                    "price_axis": {
                        "scale": "linear",
                        "verification": "verified",
                        "anchors": [
                            {**anchor, "evidence": {"kind": "manual"}}
                            for anchor in anchors
                        ],
                    },
                    "styles": [
                        {
                            "id": "up",
                            "kind": "filled",
                            "direction": "close_above_open",
                            "colors": ["#00aa00"],
                            "tolerance": 0,
                            "geometry": {
                                "min_body_width_px": 8,
                                "max_body_width_px": 15,
                                "min_body_height_px": 2,
                                "max_wick_center_offset_px": 1,
                                "max_wick_connection_gap_px": 1,
                            },
                        }
                    ],
                    "geometry": {
                        "verification": "verified",
                        "min_body_width_px": 8,
                        "max_body_width_px": 15,
                        "max_wick_center_offset_px": 1,
                    },
                    "duplicate_distance_px": 1,
                    "exclusions": {"verification": "not_applicable", "regions": []},
                    "occluders": {"verification": "not_applicable", "regions": []},
                },
            }
        ],
    }


class CandlestickUnifiedCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.spec = self.root / "figure-spec.json"
        self.output = self.root / "evidence"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_spec(self, spec: dict) -> Path:
        self.spec.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        return self.spec

    def test_extract_writes_standard_authorized_evidence_bundle(self):
        completed = run_extract(self.write_spec(ready_spec()), self.output)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            {path.name for path in self.output.iterdir()},
            {"data.csv", "report.json", "overlay.png"},
        )
        with Image.open(IMAGE) as source, Image.open(self.output / "overlay.png") as overlay:
            self.assertEqual(overlay.size, source.size)

    def test_extract_refuses_unverified_spec_without_numeric_artifacts(self):
        spec = ready_spec()
        spec["status"] = "needs_verified_configuration"
        spec["panels"][0]["confirmations"]["overlay_review"] = "proposed"

        completed = run_extract(self.write_spec(spec), self.output)

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertTrue(self.output.is_dir(), completed.stderr)
        self.assertEqual(
            {path.name for path in self.output.iterdir()},
            {"report.json"},
        )
        report = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        self.assertFalse(report["numeric_output_authorized"])
        self.assertEqual(report["refusal_reasons"], ["figure_spec_not_ready"])
        self.assertEqual(report["readiness"]["status"], "needs_verified_configuration")
        self.assertEqual(report["selected_route"], "raster_candlestick_candidate")
        self.assertEqual(report["source"]["sha256"], spec["source"]["sha256"])

    def test_extract_preserves_source_contract_mismatch_as_refusal(self):
        spec = ready_spec()
        spec["source"]["sha256"] = "0" * 64

        completed = run_extract(self.write_spec(spec), self.output)

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertTrue((self.output / "report.json").is_file(), completed.stderr)
        report = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        self.assertIn("source_contract_mismatch", report["refusal_reasons"])
        self.assertEqual({path.name for path in self.output.iterdir()}, {"report.json"})

    def test_extract_invalid_spec_writes_only_structured_refusal_report(self):
        spec = ready_spec()
        spec["source"]["width"] = -1

        completed = run_extract(self.write_spec(spec), self.output)

        self.assertNotEqual(completed.returncode, 0)
        self.assertTrue(self.output.is_dir(), completed.stderr)
        self.assertEqual({path.name for path in self.output.iterdir()}, {"report.json"})
        report = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        self.assertFalse(report["numeric_output_authorized"])
        self.assertEqual(report["refusal_reasons"], ["invalid_figure_spec"])
        self.assertTrue(report["validation_errors"])

    def test_extract_does_not_overwrite_nonempty_evidence_directory(self):
        self.output.mkdir()
        existing = self.output / "report.json"
        existing.write_text("keep", encoding="utf-8")

        completed = run_extract(self.write_spec(ready_spec()), self.output)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("non-empty evidence directory", completed.stderr)
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep")
        self.assertEqual({path.name for path in self.output.iterdir()}, {"report.json"})


if __name__ == "__main__":
    unittest.main()
