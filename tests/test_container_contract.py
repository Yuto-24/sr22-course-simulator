from __future__ import annotations

import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ContainerPythonVersionContractTests(unittest.TestCase):
    def test_dockerfile_checks_resolved_interpreter_against_python_311(self) -> None:
        dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("ARG PYTHON_VERSION=3.12", dockerfile)
        self.assertIn("FROM python:${PYTHON_VERSION}-slim-bookworm AS base", dockerfile)
        self.assertGreaterEqual(dockerfile.count("ARG PYTHON_VERSION"), 2)
        self.assertIn("actual=sys.version_info[:2]", dockerfile)
        self.assertIn("minimum=(3, 11)", dockerfile)
        self.assertIn("actual < minimum", dockerfile)
        self.assertIn("this project requires Python >= 3.11", dockerfile)
        self.assertIn(
            "COPY --chown=simulator:simulator Dockerfile compose.yaml pyproject.toml ./",
            dockerfile,
        )

    def test_compose_default_version_satisfies_project_lower_bound(self) -> None:
        compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
        match = re.search(
            r'PYTHON_VERSION:\s*"\$\{PYTHON_VERSION:-(\d+)\.(\d+)(?:\.\d+)?\}"',
            compose,
        )
        self.assertIsNotNone(match, "compose PYTHON_VERSION default is missing")
        assert match is not None
        default_version = (int(match.group(1)), int(match.group(2)))
        self.assertGreaterEqual(default_version, (3, 11))

    def test_container_check_matches_requires_python_metadata(self) -> None:
        pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('requires-python = ">=3.11"', pyproject)


if __name__ == "__main__":
    unittest.main()
