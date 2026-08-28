from pathlib import Path
import json
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from candlestick_extractor import (
    BodyCandidate,
    CandleCandidate,
    ExtractionRefused,
    FilledConfig,
    LinearPriceCalibration,
    OutlineConfig,
    WickCandidate,
    assemble_extraction,
    detect_outline_bodies,
    extract_candlesticks,
    measure_wick,
    write_extraction_artifacts,
)


FIXTURES = Path(__file__).parent / "fixtures" / "candlestick"
IMAGE = FIXTURES / "single_filled_candle.png"
CONFIG = FIXTURES / "single_filled_candle.json"


def load_fixture_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


class CandlestickExtractorContractTests(unittest.TestCase):
    def test_mismatched_source_contract_is_refused(self):
        with self.assertRaisesRegex(ExtractionRefused, "source_contract_mismatch") as refused:
            extract_candlesticks(IMAGE, {
                "source_contract": {"sha256": "0" * 64, "width": 1, "height": 1},
                "plot_bounds": [0, 0, 1, 1], "price_axis": {"scale": "linear", "anchors": []}, "styles": [],
            })
        self.assertEqual(refused.exception.reason_code, "source_contract_mismatch")

    def test_evidence_writer_refuses_nonempty_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "existing.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                write_extraction_artifacts(IMAGE, None, {}, output)

    def test_verified_fixture_writes_complete_evidence_artifacts(self):
        result, metadata = extract_candlesticks(IMAGE, load_fixture_config())
        self.assertTrue(result.numeric_output_authorized)
        self.assertEqual(len(result.candles), 1)
        candle = result.candles[0]
        self.assertGreaterEqual(candle.high, max(candle.open, candle.close))
        self.assertLessEqual(candle.low, min(candle.open, candle.close))
        with tempfile.TemporaryDirectory() as temporary:
            output = write_extraction_artifacts(IMAGE, result, metadata, Path(temporary) / "evidence")
            self.assertEqual({path.name for path in output.iterdir()}, {"data.csv", "report.json", "overlay.png"})

    def test_anchor_evidence_refusal_is_machine_readable(self):
        config = load_fixture_config()
        config["price_axis"]["require_anchor_evidence"] = True
        result, metadata = extract_candlesticks(IMAGE, config)
        self.assertFalse(result.numeric_output_authorized)
        self.assertEqual(metadata["refusal_reasons"], ["price_axis_anchor_evidence_required"])

    def test_unpaired_outline_edge_is_ambiguous_body(self):
        mask = np.zeros((20, 20), dtype=bool)
        mask[2:18, 5] = True
        candidates = detect_outline_bodies(mask, (0, 0, 19, 19), OutlineConfig("outline", 5, 10))
        self.assertEqual(candidates[0].status, "ambiguous_body")
        self.assertEqual(candidates[0].reason_code, "unpaired_outline_edge")

    def test_disconnected_center_is_ambiguous_wick(self):
        body = BodyCandidate("up", "filled", 5, 9, 7, 12, 7.0, 1.0, "candidate")
        wick = measure_wick(np.zeros((20, 20), dtype=bool), body)
        self.assertEqual(wick.status, "ambiguous_wick")
        self.assertEqual(wick.reason_code, "center_wick_not_connected")

    def test_ohlc_invariant_failure_is_recorded_in_coverage_ledger(self):
        body = BodyCandidate("up", "filled", 5, 9, 4, 6, 7.0, 1.0, "candidate")
        candidate = CandleCandidate(body, WickCandidate(5, 7, "candidate"), "close_above_open")
        result = assemble_extraction([candidate], LinearPriceCalibration.from_anchors(((0, 0), (10, 10))), duplicate_distance=1)
        self.assertFalse(result.numeric_output_authorized)
        self.assertEqual(result.coverage_ledger[0].reason_code, "ohlc_invariant_failed")
