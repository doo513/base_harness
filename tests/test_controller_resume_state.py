from harness.core.budget import Budget
from harness.core.controller import Decision, ScriptedController
from harness.core.runtime import HarnessRuntime
from harness.profiles.demo import DemoProfile


def test_scripted_controller_cursor_is_restored_before_resume_actor_call(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    decisions = [
        Decision("propose", {"key": "demo.started", "value": True}),
        Decision("verify_claim", {"key": "demo.started"}),
        Decision("complete", {"reason": "done"}),
    ]
    first_controller = ScriptedController(decisions)
    runtime = HarnessRuntime(
        goal=DemoProfile().default_goal(),
        profile=DemoProfile(),
        controller=first_controller,
        run_dir=tmp_path / "run",
        workspace=workspace,
        budget=Budget(hard_max_steps=10),
        task_revision="controller-cursor-v1",
    )

    runtime.log("run.start", {"run_id": runtime.run_id, "manifest_hash": runtime.manifest_hash})
    runtime._persist_state("manual.start")
    # Stage 05 makes step_once explicit: False means an Actor step was executed;
    # True means a kernel recovery transition consumed the step.
    assert runtime.step_once() is False
    runtime.state.step += 1
    runtime._persist_state("manual.after-first-actor")
    assert first_controller.index == 1

    resumed_controller = ScriptedController(decisions)
    resumed = HarnessRuntime.resume(
        goal=DemoProfile().default_goal(),
        profile=DemoProfile(),
        controller=resumed_controller,
        run_dir=tmp_path / "run",
        workspace=workspace,
        budget=Budget(hard_max_steps=10),
        task_revision="controller-cursor-v1",
    )

    assert resumed_controller.index == 1
    next_decision = resumed_controller.decide(
        resumed.goal.goal,
        resumed.state,
        resumed._context(),
    )
    assert next_decision.kind == "verify_claim"
    assert resumed_controller.index == 2
