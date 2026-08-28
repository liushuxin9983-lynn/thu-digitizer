import copy
import unittest

try:
    from figure_spec import (
        FigureSpecError,
        assert_valid_figure_spec,
        figure_spec_readiness,
        validate_figure_spec,
    )
except ImportError:  # pragma: no cover - package-style unittest invocation
    from .figure_spec import (
        FigureSpecError,
        assert_valid_figure_spec,
        figure_spec_readiness,
        validate_figure_spec,
    )


def base_spec():
    return {
        "schema_version": 1,
        "status": "ready_for_assisted_extraction",
        "source": {
            "media_kind": "raster",
            "coordinate_space": "pixel",
            "measurement_space": "original_raster_pixels",
            "resampling_applied": False,
            "width": 640,
            "height": 480,
            "sha256": "0" * 64,
        },
        "panels": [
            {
                "panel_id": "panel-a",
                "bounds": [20, 20, 620, 460],
                "bounds_verification": "verified",
                "plot_bounds": [40, 30, 610, 450],
                "plot_bounds_verification": "verified",
                "chart_type": "line",
                "coordinate_model": "cartesian_linear",
                "axes": [
                    {
                        "axis_id": "x",
                        "scale": "linear",
                        "verification": "verified",
                        "anchors": [{"pixel": 50, "value": 0}, {"pixel": 600, "value": 10}],
                    },
                    {
                        "axis_id": "y",
                        "scale": "linear",
                        "verification": "verified",
                        "anchors": [{"pixel": 440, "value": 0}, {"pixel": 40, "value": 100}],
                    },
                ],
                "mark_grammars": ["curve"],
                "route": {"route_id": "raster_line_color"},
                "required_confirmations": ["panel_roi", "plot_bounds", "x_axis", "y_axis"],
                "confirmations": {
                    "panel_roi": "verified",
                    "plot_bounds": "verified",
                    "x_axis": "verified",
                    "y_axis": "verified",
                },
            }
        ],
    }


def candlestick_ready_spec():
    spec = base_spec()
    panel = spec["panels"][0]
    panel.update(
        {
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
                    "anchors": [
                        {"pixel": 440, "value": 0},
                        {"pixel": 40, "value": 100},
                    ],
                },
            ],
            "mark_grammars": ["candle_body", "wick", "price_reference_line"],
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
                        {"pixel": 440, "value": 0, "evidence": {"kind": "manual"}},
                        {"pixel": 40, "value": 100, "evidence": {"kind": "manual"}},
                    ],
                },
                "styles": [
                    {
                        "id": "up",
                        "kind": "filled",
                        "colors": ["#00aa00"],
                        "tolerance": 0,
                        "direction": "close_above_open",
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
    )
    return spec


class FigureSpecTests(unittest.TestCase):
    def test_candlestick_ready_spec_is_a_valid_baseline(self):
        self.assertEqual(validate_figure_spec(candlestick_ready_spec()), [])

    def test_accepts_verified_linear_axes_and_panel_bounds(self):
        spec = base_spec()
        self.assertEqual(validate_figure_spec(spec), [])
        assert_valid_figure_spec(spec)
        self.assertEqual(figure_spec_readiness(spec)["status"], "ready_for_assisted_extraction")

    def test_rejects_out_of_bounds_panel_and_duplicate_anchor_pixels(self):
        spec = base_spec()
        spec["panels"][0]["bounds"] = [-1, 20, 620, 500]
        spec["panels"][0]["axes"][0]["anchors"][1]["pixel"] = 50
        errors = validate_figure_spec(spec)
        self.assertTrue(any("bounds" in error for error in errors))
        self.assertTrue(any("anchor pixels" in error for error in errors))
        with self.assertRaises(FigureSpecError):
            assert_valid_figure_spec(spec)

    def test_distinguishes_raw_log_values_from_displayed_log_coordinates(self):
        raw_log = base_spec()
        raw_log["panels"][0]["coordinate_model"] = "cartesian_log_x"
        raw_log["panels"][0]["axes"][0]["scale"] = "log10"
        raw_log["panels"][0]["axes"][0]["anchors"] = [
            {"pixel": 50, "value": -10},
            {"pixel": 600, "value": -2},
        ]
        self.assertTrue(any("positive" in error for error in validate_figure_spec(raw_log)))

        displayed_log = base_spec()
        displayed_log["panels"][0]["coordinate_model"] = "cartesian_displayed_log_x"
        displayed_log["panels"][0]["axes"][0]["scale"] = "displayed_log10"
        displayed_log["panels"][0]["axes"][0]["anchors"] = [
            {"pixel": 50, "value": -10},
            {"pixel": 600, "value": -2},
        ]
        self.assertEqual(validate_figure_spec(displayed_log), [])

    def test_ready_status_rejects_an_unverified_required_confirmation(self):
        spec = base_spec()
        spec["panels"][0]["confirmations"]["x_axis"] = "proposed"
        errors = validate_figure_spec(spec)
        self.assertTrue(any("x_axis" in error and "must be verified" in error for error in errors))

    def test_rejects_resampled_raster_measurement_contract(self):
        spec = base_spec()
        spec["source"]["resampling_applied"] = True
        self.assertTrue(any("resampling_applied" in error for error in validate_figure_spec(spec)))

    def test_candlestick_ready_spec_requires_linear_verified_price_axis_and_styles(self):
        spec = candlestick_ready_spec()
        spec["panels"][0]["route_config"]["price_axis"]["scale"] = "log10"
        errors = validate_figure_spec(spec)
        self.assertTrue(any("candlestick price_axis.scale" in error for error in errors))

    def test_candlestick_ready_spec_rejects_incomplete_style_or_geometry(self):
        spec = candlestick_ready_spec()
        spec["panels"][0]["route_config"]["styles"][0]["direction"] = "unknown"
        spec["panels"][0]["route_config"]["geometry"]["min_body_width_px"] = 0
        errors = validate_figure_spec(spec)
        self.assertTrue(any("candlestick styles[0].direction" in error for error in errors))
        self.assertTrue(any("candlestick geometry.min_body_width_px" in error for error in errors))

    def test_candlestick_rejects_nonfinite_or_unevidenced_route_values(self):
        spec = candlestick_ready_spec()
        config = spec["panels"][0]["route_config"]
        config["price_axis"]["anchors"][1].pop("evidence")
        config["styles"][0]["tolerance"] = float("nan")
        config["geometry"]["max_body_width_px"] = 10**10000
        errors = validate_figure_spec(spec)
        self.assertTrue(any("anchors[1]" in error for error in errors))
        self.assertTrue(any("styles[0].tolerance" in error for error in errors))
        self.assertTrue(any("geometry.max_body_width_px" in error for error in errors))

    def test_candlestick_ready_spec_requires_consistent_verified_panel_price_axis(self):
        spec = candlestick_ready_spec()
        panel = spec["panels"][0]
        panel["axes"][1]["scale"] = "log10"
        panel["route_config"]["price_axis"]["anchors"][1]["value"] = 99
        errors = validate_figure_spec(spec)
        self.assertTrue(any("candlestick panel price axis.scale" in error for error in errors))
        self.assertTrue(any("candlestick price-axis anchors" in error for error in errors))

    def test_candlestick_malformed_confirmations_return_errors(self):
        for malformed in (None, []):
            with self.subTest(confirmations=malformed):
                spec = candlestick_ready_spec()
                spec["panels"][0]["confirmations"] = malformed
                errors = validate_figure_spec(spec)
                self.assertTrue(any("confirmations must be an object" in error for error in errors))

    def test_candlestick_ready_spec_requires_resolved_geometry_and_optional_regions(self):
        spec = candlestick_ready_spec()
        config = spec["panels"][0]["route_config"]
        config["duplicate_distance_px"] = 0
        config["geometry"]["verification"] = "missing"
        config["exclusions"]["verification"] = "missing"
        config["occluders"]["verification"] = "proposed"
        errors = validate_figure_spec(spec)
        self.assertTrue(any("duplicate_distance_px" in error for error in errors))
        self.assertTrue(any("geometry.verification" in error for error in errors))
        self.assertTrue(any("exclusions.verification" in error for error in errors))
        self.assertTrue(any("occluders.verification" in error for error in errors))

    def test_candlestick_route_rejects_non_raster_source_contract(self):
        spec = candlestick_ready_spec()
        spec["source"].update(
            {
                "media_kind": "pdf",
                "coordinate_space": "pdf_pt",
                "measurement_space": "pdf_page_points",
            }
        )
        errors = validate_figure_spec(spec)
        self.assertTrue(any("candlestick source.media_kind" in error for error in errors))
        self.assertTrue(any("candlestick source.measurement_space" in error for error in errors))

    def test_candlestick_route_rejects_multiple_panels(self):
        spec = candlestick_ready_spec()
        second_panel = copy.deepcopy(spec["panels"][0])
        second_panel["panel_id"] = "panel-b"
        spec["panels"].append(second_panel)
        errors = validate_figure_spec(spec)
        self.assertTrue(any("candlestick route requires exactly one panel" in error for error in errors))

    def test_candlestick_route_rejects_wrong_coordinate_model(self):
        spec = candlestick_ready_spec()
        spec["panels"][0]["coordinate_model"] = "cartesian_linear"
        errors = validate_figure_spec(spec)
        self.assertTrue(any("candlestick coordinate_model" in error for error in errors))

    def test_candlestick_route_rejects_wrong_maturity(self):
        spec = candlestick_ready_spec()
        spec["panels"][0]["route"]["maturity"] = "validated_local_stable"
        errors = validate_figure_spec(spec)
        self.assertTrue(any("candlestick route.maturity" in error for error in errors))

    def test_candlestick_route_rejects_empty_anchor_evidence(self):
        spec = candlestick_ready_spec()
        spec["panels"][0]["route_config"]["price_axis"]["anchors"][0]["evidence"] = {}
        errors = validate_figure_spec(spec)
        self.assertTrue(any("anchors[0]" in error for error in errors))

    def test_candlestick_ready_spec_rejects_missing_category_axis(self):
        spec = candlestick_ready_spec()
        spec["panels"][0]["axes"] = [spec["panels"][0]["axes"][1]]
        errors = validate_figure_spec(spec)
        self.assertTrue(any("candlestick panel requires exactly one category axis" in error for error in errors))

    def test_candlestick_ready_spec_rejects_wrong_category_axis_contract(self):
        spec = candlestick_ready_spec()
        category_axis = spec["panels"][0]["axes"][0]
        category_axis["scale"] = "linear"
        category_axis["verification"] = "verified"
        errors = validate_figure_spec(spec)
        self.assertTrue(any("candlestick category axis.scale" in error for error in errors))
        self.assertTrue(any("candlestick category axis.verification" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
