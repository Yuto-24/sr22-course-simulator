from __future__ import annotations

import json
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = REPOSITORY_ROOT / "notebooks" / "spiral_descent_walkthrough.ipynb"


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


if __name__ == "__main__":
    unittest.main()
