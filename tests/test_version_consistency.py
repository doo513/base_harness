from __future__ import annotations

from pathlib import Path
import tomllib

import harness


def test_runtime_and_build_metadata_versions_match():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == harness.__version__
