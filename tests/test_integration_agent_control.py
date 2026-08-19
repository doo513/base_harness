import pytest

from harness.core.agent_control import AgentControlError, AgentControlState, AgentTaskStatus
from harness.core.budget import Budget
from harness.core.controller import Decision, ScriptedController
from harness.core.progress import decision_progress_signatures
from harness.core.runtime import HarnessRuntime
from harness.core.state import HarnessState
from harness.profiles.software import SoftwareProfile


def _plan():
    return [
        {"id": "inspect", "title": "Inspect repository", "depends_on": []},
        {"id": "implement", "title": "Implement change", "depends_on": ["inspect"]},
        {"id": "verify", "title": "Run verification", "depends_on": ["implement"]},
    ]


def test_agent_control_rejects_cycles_and_unfinished_dependency_activation():
    state = AgentControlState()
    with pytest.raises(AgentControlError):
        state.replace_plan("bad", [
            {"id": "a", "title": "A", "depends_on": ["b"]},
            {"id": "b", "title": "B", "depends_on": ["a"]},
        ])

    state.replace_plan("deliver change", _plan())
    with pytest.raises(AgentControlError):
        state.activate("implement")
    state.activate("inspect")
    state.update("inspect", status="done", note="repository inspected")
    state.activate("implement")
    assert state.active_task_id == "implement"
    assert state.tasks["implement"].status == AgentTaskStatus.ACTIVE


def test_agent_control_snapshot_round_trip_is_non_authoritative():
    state = HarnessState()
    state.agent_control.replace_plan("deliver change", _plan())
    state.agent_control.activate("inspect")
    restored = HarnessState.from_snapshot(state.snapshot())
    assert restored.agent_control.dump() == state.agent_control.dump()
    view = restored.agent_control.context_view()
    assert view["instruction_authority"] == "none"
    assert view["progress_authority"] is False
    assert view["completion_authority"] is False


def test_plan_and_task_decisions_do_not_modify_truth_completion_or_progress_credit(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = SoftwareProfile(workspace=workspace, acceptance_commands=["false"])
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=tmp_path / "run",
        workspace=workspace,
        budget=Budget(hard_max_steps=5),
    )
    before_progress = runtime.state.progress.dump()

    plan = Decision("plan", {"objective": "deliver change", "tasks": _plan()})
    plan.validate()
    runtime._dispatch_decision(plan)
    task = Decision("task", {"id": "inspect", "status": "active"})
    task.validate()
    runtime._dispatch_decision(task)

    assert runtime.state.facts == {}
    assert runtime.state.hypotheses == {}
    assert runtime.state.completed is False
    assert runtime.state.progress.dump() == before_progress
    assert runtime.state.agent_control.active_task_id == "inspect"

    context = runtime._context()
    assert context["agent_workflow"]["active_task_id"] == "inspect"
    assert context["agent_workflow"]["progress_authority"] is False


def test_plan_and_task_decisions_are_activity_only_for_stage06_progress_identity():
    plan = Decision("plan", {"objective": "x", "tasks": [{"id": "a", "title": "A", "depends_on": []}]})
    task = Decision("task", {"id": "a", "status": "done"})
    assert decision_progress_signatures(plan)[0] == "plan"
    assert decision_progress_signatures(task)[0] == "task"
