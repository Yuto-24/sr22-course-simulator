from __future__ import annotations

import json
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = REPOSITORY_ROOT / "notebooks" / "spiral_descent_walkthrough.ipynb"
TRAFFIC_PATTERN_NOTEBOOK_PATH = (
    REPOSITORY_ROOT / "notebooks" / "miyazaki_traffic_patterns.ipynb"
)


class NotebookContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        """
        Load the notebook definition and its cells for the test class.
        """
        cls.notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
        cls.cells = cls.notebook["cells"]

    def test_notebook_has_python_kernel_and_tutorial_section_order(self) -> None:
        self.assertEqual(self.notebook["nbformat"], 4)
        self.assertEqual(self.notebook["metadata"]["kernelspec"]["name"], "python3")

        markdown = "\n".join(
            "".join(cell["source"])
            for cell in self.cells
            if cell["cell_type"] == "markdown"
        )
        section_positions = [
            markdown.index(section)
            for section in ("## Goal", "## Setup", "## Steps", "## Checks", "## Next Steps")
        ]
        self.assertEqual(section_positions, sorted(section_positions))

    def test_parameter_cell_separates_inputs_and_explicit_assumptions(self) -> None:
        parameter_cells = [
            cell
            for cell in self.cells
            if "parameters" in cell.get("metadata", {}).get("tags", [])
        ]
        self.assertEqual(len(parameter_cells), 1)
        source = "".join(parameter_cells[0]["source"])
        for expected in (
            "# InitialState: 編集可能",
            "# Environment: 気象風向は FROM",
            "# Explicit assumptions:",
            "interpret_unspecified_airspeed_as_tas = True",
            "wind_from_deg_true",
            "wind_speed_kt",
        ):
            self.assertIn(expected, source)

    def test_notebook_keeps_reference_path_separate_and_exports_artifacts(self) -> None:
        code = "\n".join(
            "".join(cell["source"])
            for cell in self.cells
            if cell["cell_type"] == "code"
        )
        self.assertIn("spiral_descent_package()", code)
        self.assertIn("maneuver_spec.termination_conditions", code)
        self.assertIn('item.value is not None', code)
        self.assertIn('if completion.unit != "deg":', code)
        self.assertNotIn("target_turns", code)
        self.assertNotIn("AccumulatedTurn", code)
        self.assertIn("PylonSpiralPath(", code)
        self.assertIn("reference_path=reference_path", code)
        self.assertIn("termination=None", code)
        self.assertIn("write_trajectory_csv(", code)
        self.assertIn("trajectory_to_kml(", code)
        self.assertIn("reference_path_to_kml(", code)
        self.assertIn('artifact_dir / "guided-trajectory.csv"', code)
        self.assertIn('artifact_dir / "guided-reference-path.kml"', code)

    def test_committed_notebook_is_clean_and_all_code_cells_compile(self) -> None:
        """Verify that all notebook code cells are unexecuted, contain no outputs, and compile successfully."""
        for index, cell in enumerate(self.cells):
            if cell["cell_type"] != "code":
                continue
            self.assertIsNone(cell["execution_count"])
            self.assertEqual(cell["outputs"], [])
            compile("".join(cell["source"]), f"notebook-cell-{index}", "exec")

    def test_documentation_covers_windows_powershell_workflows(self) -> None:
        """Verify that Windows users do not have to translate POSIX-only commands."""

        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        workflow = (REPOSITORY_ROOT / "docs" / "notebook-workflow.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(r".\.venv\Scripts\python.exe", readme)
        self.assertIn("New-Item -ItemType Directory -Force artifacts", readme)
        self.assertIn(r".\.venv\Scripts\python.exe", workflow)
        self.assertIn('$env:JUPYTER_PORT = "8890"', workflow)


class TrafficPatternNotebookContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.notebook = json.loads(
            TRAFFIC_PATTERN_NOTEBOOK_PATH.read_text(encoding="utf-8")
        )
        cls.cells = cls.notebook["cells"]

    def test_required_sections_are_in_workflow_order(self) -> None:
        markdown = "\n".join(
            "".join(cell["source"])
            for cell in self.cells
            if cell["cell_type"] == "markdown"
        )
        section_positions = [
            markdown.index(section)
            for section in (
                "## 1. AirportSpec",
                "## 2. RWY True Bearing",
                "## 3. RWY Center Point",
                "## 4. Pattern parameters",
                "## 5. 通常場周と独立Circle／270 Path",
                "## 6. 簡易可視化",
                "## 7. KML 出力",
            )
        ]
        self.assertEqual(section_positions, sorted(section_positions))

    def test_parameter_cell_exposes_all_requested_values(self) -> None:
        parameter_cells = [
            cell
            for cell in self.cells
            if "parameters" in cell.get("metadata", {}).get("tags", [])
        ]
        self.assertEqual(len(parameter_cells), 1)
        source = "".join(parameter_cells[0]["source"])
        for expected in (
            "PATTERN_ALTITUDE_FT = 1000.0",
            "DOWNWIND_OFFSET_NM = 1.5",
            "CROSSWIND_BASE_EXTENSION_NM = 1.2",
            "TRUE_AIRSPEED_KT = 110.0",
            "NORMAL_BANK_DEG = 22.0",
            "DOWNWIND_TURN_BANK_DEG = 22.0",
            "BASE_TURN_BANK_DEG = 22.0",
            "FINAL_BANK_DEG = 25.0",
            "ROLL_RATE_DEG_S = 10.0",
            "GLIDE_PATH_DEG = 3.0",
            "SAMPLE_INTERVAL_S = 0.25",
            "SHORT_DOWNWIND_CIRCLE_TRUE_AIRSPEED_KT = 110.0",
            "SHORT_DOWNWIND_CIRCLE_BANK_DEG = 22.0",
            "RWY09_LINE_COLOR = 'ffffff00'",
            "RWY09_FILL_COLOR = '1affffcc'",
            "RWY27_LINE_COLOR = 'ff00aaff'",
            "RWY27_FILL_COLOR = '1a80d4ff'",
            "MAGNETIC_REFERENCE_YEAR = 2026.0",
        ):
            self.assertIn(expected, source)
        for switch_name in (
            "MAKE_CIRCLE_BEFORE_DOWNWIND",
            "MAKE_CIRCLE_MIDDLE_DOWNWIND",
            "MAKE_CIRCLE_BEFORE_BASE",
            "MAKE_270_BEFORE_DOWNWIND",
            "MAKE_270_BEFORE_BASE",
        ):
            self.assertRegex(source, rf"{switch_name} = (True|False)")

    def test_notebook_uses_center_based_generator_and_expected_kml_writer(self) -> None:
        code = "\n".join(
            "".join(cell["source"])
            for cell in self.cells
            if cell["cell_type"] == "code"
        )
        self.assertIn("runway.center_point", code)
        self.assertIn("build_rjfm_traffic_pattern_components(", code)
        self.assertIn("write_rjfm_traffic_pattern_kmls(", code)
        self.assertIn("build_rjfm_short_downwind_paths(", code)
        self.assertIn("write_rjfm_short_downwind_kmls(", code)
        self.assertEqual(code.count("make_circle_before_downwind=MAKE_CIRCLE_BEFORE_DOWNWIND"), 3)
        self.assertEqual(code.count("make_circle_middle_downwind=MAKE_CIRCLE_MIDDLE_DOWNWIND"), 3)
        self.assertEqual(code.count("make_circle_before_base=MAKE_CIRCLE_BEFORE_BASE"), 3)
        self.assertEqual(
            code.count("make_270_before_downwind=MAKE_270_BEFORE_DOWNWIND"),
            3,
        )
        self.assertEqual(code.count("make_270_before_base=MAKE_270_BEFORE_BASE"), 3)
        self.assertEqual(
            code.count("downwind_turn_bank_deg=DOWNWIND_TURN_BANK_DEG"),
            3,
        )
        self.assertEqual(code.count("base_turn_bank_deg=BASE_TURN_BANK_DEG"), 3)
        for color_parameter in (
            "rwy09_line_color=RWY09_LINE_COLOR",
            "rwy09_fill_color=RWY09_FILL_COLOR",
            "rwy27_line_color=RWY27_LINE_COLOR",
            "rwy27_fill_color=RWY27_FILL_COLOR",
        ):
            self.assertIn(color_parameter, code)
        self.assertEqual(
            code.count(
                "circle_true_airspeed_kt=SHORT_DOWNWIND_CIRCLE_TRUE_AIRSPEED_KT"
            ),
            2,
        )
        self.assertEqual(
            code.count("circle_bank_deg=SHORT_DOWNWIND_CIRCLE_BANK_DEG"),
            2,
        )
        self.assertIn("normal_turn_radius_m", code)
        self.assertIn("final_turn_radius_m", code)
        self.assertIn("RJFM_PATTERN_FILENAMES", code)
        self.assertIn("expected_component_count", code)
        self.assertNotIn("ConstantWind", code)
        self.assertNotIn("NoWind", code)

    def test_committed_notebook_is_clean_and_all_code_cells_compile(self) -> None:
        self.assertEqual(self.notebook["nbformat"], 4)
        self.assertEqual(self.notebook["metadata"]["kernelspec"]["name"], "python3")
        for index, cell in enumerate(self.cells):
            if cell["cell_type"] != "code":
                continue
            self.assertIsNone(cell["execution_count"])
            self.assertEqual(cell["outputs"], [])
            compile("".join(cell["source"]), f"traffic-notebook-cell-{index}", "exec")


if __name__ == "__main__":
    unittest.main()
