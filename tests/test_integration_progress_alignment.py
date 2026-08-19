from harness.core.controller import Decision, ScriptedController
from harness.core.runtime import HarnessRuntime
from harness.core.state import Authority, Claim, ClaimStatus
from harness.profiles.software import SoftwareProfile


def _runtime(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = SoftwareProfile(workspace=workspace, acceptance_commands=["false"])
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=tmp_path / "run",
        workspace=workspace,
    )
    return runtime


def test_actor_task_bookkeeping_does_not_reset_progress(tmp_path):
    runtime = _runtime(tmp_path)
    baseline = runtime._progress_baseline()
    decision = Decision("task", {"id": "inspect", "status": "done"})
    result = runtime._evaluate_actor_progress(decision, baseline, allow_trigger=False)
    assert result["made_progress"] is False
    assert runtime.state.progress.no_progress_streak == 1


def test_verified_software_milestone_resets_progress(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.state.progress.no_progress_streak = 3
    baseline = runtime._progress_baseline()
    runtime.state.facts["software.test_result.target"] = Claim(
        "software.test_result.target",
        {"succeeded": True},
        status=ClaimStatus.VERIFIED,
        authority=Authority.ENVIRONMENT,
    )
    decision = Decision("propose", {"key": "irrelevant", "value": True})
    result = runtime._evaluate_actor_progress(decision, baseline, allow_trigger=True)
    assert result["made_progress"] is True
    assert "profile_task_progress_advanced" in result["progress_reasons"]
    assert runtime.state.progress.no_progress_streak == 0
    assert runtime.state.progress.task_events >= 1
