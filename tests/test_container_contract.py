from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
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
            "COPY --chown=simulator:simulator Dockerfile README.md compose.yaml compose.host.yaml pyproject.toml ./",
            dockerfile,
        )
        self.assertIn("COPY --chown=simulator:simulator docs/ ./docs/", dockerfile)
        self.assertIn("COPY --chown=simulator:simulator notebooks/ ./notebooks/", dockerfile)

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
        """Verify that project metadata requires Python 3.11 or newer."""
        pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('requires-python = ">=3.11"', pyproject)

    def test_notebook_image_uses_declared_extra_and_non_root_runtime(self) -> None:
        dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
        pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        notebook_stage = dockerfile.split("FROM base AS notebook", maxsplit=1)[1].split(
            "FROM base AS runtime", maxsplit=1
        )[0]
        self.assertIn('notebook = [', pyproject)
        self.assertIn('"jupyterlab>=4.4,<5"', pyproject)
        self.assertIn('"nbconvert>=7.16"', pyproject)
        self.assertIn('python -m pip install --no-cache-dir ".[notebook]"', notebook_stage)
        for runtime_directory in (
            "/tmp/simulator-home",
            "/tmp/ipython",
            "/tmp/jupyter/config",
            "/tmp/jupyter/data",
            "/tmp/jupyter/runtime",
            "/tmp/matplotlib",
        ):
            self.assertIn(runtime_directory, notebook_stage)
        self.assertIn("/tmp/simulator-home /tmp/ipython /tmp/jupyter /tmp/matplotlib", notebook_stage)
        self.assertIn("USER simulator", notebook_stage)
        self.assertIn("EXPOSE 8888", notebook_stage)

    def test_compose_notebook_persists_notebook_and_artifacts(self) -> None:
        compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")

        self.assertIn("target: notebook", compose)
        self.assertIn('"${JUPYTER_HOST:-127.0.0.1}:${JUPYTER_PORT:-8888}:8888"', compose)
        self.assertIn(
            'JUPYTER_TOKEN: "${JUPYTER_TOKEN:-}"',
            compose,
        )
        self.assertNotIn("--ServerApp.password=", compose)
        self.assertIn("source: ./notebooks", compose)
        self.assertIn("target: /workspace/notebooks", compose)
        self.assertIn("source: ./artifacts", compose)
        self.assertIn("target: /output", compose)
        self.assertIn("SR22_ARTIFACT_DIR: /output", compose)

    def test_notebook_entrypoint_requires_token_only_at_startup(self) -> None:
        compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
        # Execute the actual shell block after Compose's dollar unescaping.
        block = compose.split("      - |\n", 1)[1].split(
            "      - notebook-entrypoint", 1
        )[0]
        script = textwrap.dedent(block).replace("$$", "$")
        environment = dict(os.environ)
        environment.pop("JUPYTER_TOKEN", None)
        for token in (None, "", "test token $literal; 'quoted' \"value\""):
            with self.subTest(token_present=bool(token)):
                if token is not None:
                    environment["JUPYTER_TOKEN"] = token
                result = subprocess.run(
                    ["/bin/sh", "-ec", script, "notebook-entrypoint",
                     sys.executable, "-c",
                     "import json, sys; print(json.dumps(sys.argv[1:]))",
                     "--existing-argument"],
                    env=environment, capture_output=True, text=True,
                )
                if token:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), [
                        "--existing-argument", f"--ServerApp.token={token}",
                    ])
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Set JUPYTER_TOKEN", result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_host_network_override_resets_parent_port_mapping(self) -> None:
        host_compose = (REPOSITORY_ROOT / "compose.host.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn("network_mode: host", host_compose)
        self.assertIn("ports: !reset []", host_compose)


if __name__ == "__main__":
    unittest.main()
