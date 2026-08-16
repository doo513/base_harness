from pathlib import Path

from harness.core.controller import Decision, ScriptedController
from harness.core.tools import ActionRuntime, ToolSpec, ToolCall, SideEffect, make_shell_tool
from harness.core.runtime import HarnessRuntime
from harness.core.budget import Budget
from harness.profiles.software import SoftwareProfile


def test_shell_nonzero_exit_is_failure(tmp_path):
    runtime = ActionRuntime({"shell": make_shell_tool(tmp_path)})
    result = runtime.execute(ToolCall("shell", {"command": "exit 1"}))
    assert result.ok is False
    assert result.output["returncode"] == 1


def test_confirm_permission_is_fail_closed_without_approval():
    called = {"n": 0}

    def handler():
        called["n"] += 1
        return "ok"

    runtime = ActionRuntime({
        "danger": ToolSpec(
            name="danger",
            description="side effect",
            handler=handler,
            side_effect=SideEffect.EXTERNAL,
            permission="confirm",
        )
    })
    result = runtime.execute(ToolCall("danger", {}))
    assert result.ok is False
    assert result.approval_required is True
    assert called["n"] == 0


def test_confirm_permission_runs_only_with_explicit_approval():
    called = {"n": 0}

    def handler():
        called["n"] += 1
        return "ok"

    spec = ToolSpec(
        name="danger",
        description="side effect",
        handler=handler,
        side_effect=SideEffect.EXTERNAL,
        permission="confirm",
    )
    runtime = ActionRuntime(
        {"danger": spec},
        approval_checker=lambda call, tool: call.tool == "danger",
    )
    result = runtime.execute(ToolCall("danger", {}))
    assert result.ok is True
    assert called["n"] == 1


def test_malformed_decision_becomes_failure_not_crash(tmp_path):
    profile = SoftwareProfile(workspace=tmp_path, acceptance_commands=["false"])
    controller = ScriptedController([
        Decision("propose", {}),
    ])
    state = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller,
        run_dir=tmp_path / "run",
        workspace=tmp_path,
        budget=Budget(hard_max_steps=1),
    ).run()
    assert not state.completed
    assert any(f["kind"] == "implementation_error" for f in state.failures)


def test_unrelated_tool_artifact_cannot_verify_arbitrary_claim(tmp_path):
    profile = SoftwareProfile(workspace=tmp_path, acceptance_commands=["false"])

    # First run one tool call and capture its artifact.
    first = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([
            Decision("tool", {"tool": "shell", "args": {"command": "printf hello"}}),
        ]),
        run_dir=tmp_path / "run1",
        workspace=tmp_path,
        budget=Budget(hard_max_steps=1),
    ).run()
    ref = first.observations[0].artifact_ref

    # Re-use that unrelated artifact to support an arbitrary claim.
    second = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([
            Decision("propose", {
                "key": "security.sql_injection_success",
                "value": True,
                "evidence_refs": [ref],
            }),
            Decision("verify_claim", {"key": "security.sql_injection_success"}),
        ]),
        run_dir=tmp_path / "run2",
        workspace=tmp_path,
        budget=Budget(hard_max_steps=2),
    ).run()
    assert "security.sql_injection_success" not in second.facts


def test_refuted_hypothesis_requires_new_evidence_to_reopen(tmp_path):
    profile = SoftwareProfile(workspace=tmp_path, acceptance_commands=["false"])
    controller = ScriptedController([
        Decision("propose", {"key": "h", "value": 1}),
        Decision("refute", {"key": "h", "reason": "wrong"}),
        Decision("propose", {"key": "h", "value": 1}),
    ])
    state = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller,
        run_dir=tmp_path / "run",
        workspace=tmp_path,
        budget=Budget(hard_max_steps=3),
    ).run()
    assert "h" in state.refuted_hypotheses
    assert "h" not in state.hypotheses
    assert any(f["kind"] == "hypothesis_refuted" for f in state.failures)
