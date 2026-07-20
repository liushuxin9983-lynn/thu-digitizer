import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from candidate_digitize_bar_chart import _data_to_pixel, extract_bar_chart


RED = "#d62728"
BLUE = "#1f77b4"
GREEN = "#2ca02c"
ERROR = "#6e6e6e"


def rgb(value):
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))


def save_image(directory, image):
    path = Path(directory) / "chart.png"
    Image.fromarray(image, mode="RGB").save(path)
    return path


def paint_vertical_bar(image, center, width, value, axis, color, baseline=0.0):
    start = round(_data_to_pixel(baseline, axis))
    end = round(_data_to_pixel(value, axis))
    image[min(start, end) : max(start, end), center - width // 2 : center + width // 2] = rgb(color)


def paint_horizontal_bar(image, center, height, value, axis, color, baseline=0.0):
    start = round(_data_to_pixel(baseline, axis))
    end = round(_data_to_pixel(value, axis))
    image[center - height // 2 : center + height // 2, min(start, end) : max(start, end)] = rgb(color)


class CandidateBarExtractorTests(unittest.TestCase):
    def test_extracts_vertical_grouped_positive_and_negative_bars(self):
        image = np.full((120, 180, 3), 255, dtype=np.uint8)
        value_axis = (10.0, 10.0, 110.0, -10.0)
        categories = [("A", 40.0), ("B", 90.0), ("C", 140.0)]
        truth = {
            RED: [6.0, -4.0, 8.0],
            BLUE: [3.0, 5.0, -6.0],
        }
        for (_, category_pixel), red_value, blue_value in zip(
            categories, truth[RED], truth[BLUE]
        ):
            paint_vertical_bar(
                image, round(category_pixel) - 8, 12, red_value, value_axis, RED
            )
            paint_vertical_bar(
                image, round(category_pixel) + 8, 12, blue_value, value_axis, BLUE
            )

        with tempfile.TemporaryDirectory() as directory:
            path = save_image(directory, image)
            report = extract_bar_chart(
                path,
                plot_bounds=(10, 10, 169, 109),
                value_axis=value_axis,
                orientation="vertical",
                layout="grouped",
                series_colors={"red": RED, "blue": BLUE},
                categories=categories,
                tolerance=1,
            )

        self.assertEqual(report["status"], "candidate")
        extracted = {
            (mark["category"], mark["series"]): mark["value"]
            for mark in report["marks"]
        }
        for category_index, (category, _) in enumerate(categories):
            self.assertAlmostEqual(extracted[(category, "red")], truth[RED][category_index])
            self.assertAlmostEqual(extracted[(category, "blue")], truth[BLUE][category_index])

    def test_extracts_horizontal_grouped_bars_and_visible_error_intervals(self):
        image = np.full((130, 190, 3), 255, dtype=np.uint8)
        value_axis = (10.0, -10.0, 170.0, 10.0)
        categories = [("A", 35.0), ("B", 65.0), ("C", 95.0)]
        values = {"red": [-3.0, 4.0, 6.0], "blue": [2.0, -5.0, 3.0]}
        colors = {"red": RED, "blue": BLUE}
        for category_index, (_, category_pixel) in enumerate(categories):
            for series_index, series in enumerate(("red", "blue")):
                center = round(category_pixel) + (-6 if series_index == 0 else 6)
                value = values[series][category_index]
                paint_horizontal_bar(
                    image, center, 10, value, value_axis, colors[series]
                )
                lower = round(_data_to_pixel(value - 1.0, value_axis))
                upper = round(_data_to_pixel(value + 1.0, value_axis))
                first, second = sorted((lower, upper))
                image[center, first : second + 1] = rgb(ERROR)
                image[center - 2 : center + 3, first] = rgb(ERROR)
                image[center - 2 : center + 3, second] = rgb(ERROR)

        with tempfile.TemporaryDirectory() as directory:
            path = save_image(directory, image)
            report = extract_bar_chart(
                path,
                plot_bounds=(10, 10, 179, 119),
                value_axis=value_axis,
                orientation="horizontal",
                layout="grouped",
                series_colors=colors,
                categories=categories,
                tolerance=1,
                error_color=ERROR,
                error_tolerance=1,
                error_search_radius=1,
            )

        self.assertEqual(report["status"], "candidate")
        for mark in report["marks"]:
            expected = values[mark["series"]][
                [name for name, _ in categories].index(mark["category"])
            ]
            self.assertAlmostEqual(mark["value"], expected)
            self.assertEqual(mark["error_bar"]["status"], "extracted")
            self.assertAlmostEqual(mark["error_bar"]["lower_value"], expected - 1.0)
            self.assertAlmostEqual(mark["error_bar"]["upper_value"], expected + 1.0)

    def test_extracts_percent_stacks_as_visible_segments(self):
        image = np.full((125, 180, 3), 255, dtype=np.uint8)
        value_axis = (10.0, 100.0, 110.0, 0.0)
        categories = [("A", 50.0), ("B", 130.0)]
        colors = {"red": RED, "blue": BLUE, "green": GREEN}
        truth = {
            "A": {"red": 20.0, "blue": 30.0, "green": 50.0},
            "B": {"red": 40.0, "blue": 10.0, "green": 50.0},
        }
        for category, category_pixel in categories:
            cumulative = 0.0
            for series, color in colors.items():
                next_total = cumulative + truth[category][series]
                start = round(_data_to_pixel(cumulative, value_axis))
                end = round(_data_to_pixel(next_total, value_axis))
                image[
                    min(start, end) : max(start, end),
                    round(category_pixel) - 10 : round(category_pixel) + 10,
                ] = rgb(color)
                cumulative = next_total

        with tempfile.TemporaryDirectory() as directory:
            path = save_image(directory, image)
            report = extract_bar_chart(
                path,
                plot_bounds=(10, 10, 169, 110),
                value_axis=value_axis,
                orientation="vertical",
                layout="percent_stacked",
                series_colors=colors,
                categories=categories,
                tolerance=1,
            )

        self.assertEqual(report["status"], "candidate")
        self.assertTrue(
            all(
                diagnostic["within_tolerance"]
                for diagnostic in report["stack_diagnostics"]
                if diagnostic["kind"] == "stack_total"
            )
        )
        for mark in report["marks"]:
            self.assertAlmostEqual(
                mark["value"], truth[mark["category"]][mark["series"]]
            )

    def test_refuses_multiple_rectangles_for_one_series_category(self):
        image = np.full((100, 120, 3), 255, dtype=np.uint8)
        value_axis = (10.0, 10.0, 90.0, -10.0)
        paint_vertical_bar(image, 50, 10, 4.0, value_axis, RED)
        paint_vertical_bar(image, 70, 10, 6.0, value_axis, RED)

        with tempfile.TemporaryDirectory() as directory:
            path = save_image(directory, image)
            report = extract_bar_chart(
                path,
                plot_bounds=(10, 10, 109, 90),
                value_axis=value_axis,
                orientation="vertical",
                layout="grouped",
                series_colors={"red": RED},
                categories=[("A", 60.0)],
                tolerance=1,
            )

        self.assertEqual(report["status"], "low_confidence")
        self.assertEqual(report["marks"][0]["status"], "low_confidence")
        self.assertNotIn("value", report["marks"][0])

    def test_verified_exclusion_region_removes_in_plot_legend_swatch(self):
        image = np.full((120, 140, 3), 255, dtype=np.uint8)
        value_axis = (10.0, 10.0, 110.0, -10.0)
        categories = [("A", 70.0)]
        paint_vertical_bar(image, 62, 12, 6.0, value_axis, RED)
        paint_vertical_bar(image, 78, 12, 4.0, value_axis, BLUE)
        image[12:20, 50:62] = rgb(RED)
        image[22:30, 50:62] = rgb(BLUE)

        with tempfile.TemporaryDirectory() as directory:
            path = save_image(directory, image)
            report = extract_bar_chart(
                path,
                plot_bounds=(10, 10, 129, 110),
                value_axis=value_axis,
                orientation="vertical",
                layout="grouped",
                series_colors={"red": RED, "blue": BLUE},
                categories=categories,
                tolerance=1,
                exclude_regions=[(48, 11, 64, 29)],
            )

        self.assertEqual(report["status"], "candidate")
        self.assertEqual(report["summary"]["excluded_component_count"], 2)
        values = {mark["series"]: mark["value"] for mark in report["marks"]}
        self.assertAlmostEqual(values["red"], 6.0)
        self.assertAlmostEqual(values["blue"], 4.0)

    def test_missing_colour_is_not_converted_to_zero(self):
        image = np.full((100, 120, 3), 255, dtype=np.uint8)
        value_axis = (10.0, 10.0, 90.0, -10.0)
        paint_vertical_bar(image, 60, 12, 4.0, value_axis, RED)

        with tempfile.TemporaryDirectory() as directory:
            path = save_image(directory, image)
            report = extract_bar_chart(
                path,
                plot_bounds=(10, 10, 109, 90),
                value_axis=value_axis,
                orientation="vertical",
                layout="grouped",
                series_colors={"red": RED, "blue": BLUE},
                categories=[("A", 60.0)],
                tolerance=1,
            )

        self.assertEqual(report["status"], "partial_visible")
        missing = next(mark for mark in report["marks"] if mark["series"] == "blue")
        self.assertEqual(missing["status"], "not_extracted")
        self.assertNotIn("value", missing)

    def test_bridges_gridline_gap_and_prefers_baseline_connected_bar_over_legend(self):
        image = np.full((140, 160, 3), 255, dtype=np.uint8)
        value_axis = (12.0, 10.0, 128.0, -10.0)
        # The real bar has two white raster/gridline gaps along its value axis.
        paint_vertical_bar(image, 80, 20, 6.0, value_axis, RED)
        image[67, 70:91] = 255
        image[69, 70:91] = 255
        # A same-colour legend swatch lies in the plot ROI but does not touch
        # the calibrated baseline; it must not become the extracted bar.
        image[20:28, 20:36] = rgb(RED)

        with tempfile.TemporaryDirectory() as directory:
            path = save_image(directory, image)
            report = extract_bar_chart(
                path,
                plot_bounds=(12, 12, 148, 128),
                value_axis=value_axis,
                orientation="vertical",
                layout="grouped",
                series_colors={"red": RED},
                categories=[("A", 80.0)],
                tolerance=1,
                min_area=20,
                min_bar_thickness=8,
                min_bar_length=10,
                value_gap=2,
                prefer_baseline_connected=True,
            )

        self.assertEqual(report["status"], "partial_visible")
        self.assertAlmostEqual(report["marks"][0]["value"], 6.0, delta=0.25)
        self.assertNotEqual(report["marks"][0]["component"]["top_pixel"], 20)


if __name__ == "__main__":
    unittest.main()
