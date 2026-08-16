from __future__ import annotations

import pytest

from harness.core.budget import Budget
from harness.core.controller import ScriptedController
from harness.core.runtime import HarnessRuntime
from harness.core.storage import ResumeConflict
from harness.profiles.demo import DemoProfile


def test_resume_rejects_harness_version_drift(tmp_path, monkeypatch):
    profile = DemoProfile()
    run_dir = tmp_path / "run"
    HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=run_dir,
        workspace=tmp_path,
        budget=Budget(hard_max_steps=0),
    ).run()

    import harness.core.runtime as runtime_module
    monkeypatch.setattr(runtime_module, "__version__", "999.0.0-drift")

    with pytest.raises(ResumeConflict, match="harness version differs"):
        HarnessRuntime.resume(
            goal=profile.default_goal(),
            profile=profile,
            controller=ScriptedController([]),
            run_dir=run_dir,
            workspace=tmp_path,
            budget=Budget(hard_max_steps=0),
        )
