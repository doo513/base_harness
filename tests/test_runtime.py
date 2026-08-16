import json
from harness.core.controller import Decision, ScriptedController
from harness.core.runtime import HarnessRuntime
from harness.core.contracts import GoalContract
from harness.core.budget import Budget
from harness.profiles.demo import DemoProfile
from harness.profiles.software import SoftwareProfile

def test_demo_oracle_accepts_only_after_verified_fact(tmp_path):
    controller = ScriptedController([
        Decision("propose", {"key": "demo.started", "value": True}),
        Decision("verify_claim", {"key": "demo.started"}),
        Decision("complete", {"reason": "done"}),
    ])
    state = HarnessRuntime(
        goal=DemoProfile().default_goal(),
        profile=DemoProfile(),
        controller=controller,
        run_dir=tmp_path,
        budget=Budget(hard_max_steps=10),
    ).run()
    assert state.completed
    assert state.facts["demo.started"].status.value == "verified"
    assert (tmp_path / "events.jsonl").exists()
    assert (tmp_path / "checkpoint.json").exists()
    assert (tmp_path / "metrics.json").exists()

def test_actor_complete_cannot_bypass_oracle(tmp_path):
    profile = SoftwareProfile(workspace=tmp_path, acceptance_commands=["false"])
    controller = ScriptedController([Decision("complete", {"reason": "trust me"})])
    state = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller,
        run_dir=tmp_path / "run",
        workspace=tmp_path,
        budget=Budget(hard_max_steps=1),
    ).run()
    assert not state.completed
    assert any("completion oracle rejected" in f["message"] for f in state.failures)

def test_fixed_command_oracle_can_accept(tmp_path):
    profile = SoftwareProfile(workspace=tmp_path, acceptance_commands=["true"])
    controller = ScriptedController([Decision("complete", {"reason": "run acceptance"})])
    state = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller,
        run_dir=tmp_path / "run",
        workspace=tmp_path,
        budget=Budget(hard_max_steps=2),
    ).run()
    assert state.completed

def test_tool_call_trace_and_artifact(tmp_path):
    profile = SoftwareProfile(workspace=tmp_path, acceptance_commands=["true"])
    controller = ScriptedController([
        Decision("tool", {"tool": "shell", "args": {"command": "printf hello"}}),
        Decision("complete", {"reason": "done"}),
    ])
    state = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller,
        run_dir=tmp_path / "run",
        workspace=tmp_path,
        budget=Budget(hard_max_steps=3),
    ).run()
    lines = (tmp_path / "run" / "tool_calls.jsonl").read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["tool"] == "shell"
    assert record["ok"] is True
    assert state.observations[0].artifact_ref
    assert "hello" in state.observations[0].preview["stdout"]

def test_unverified_tool_observation_does_not_become_fact(tmp_path):
    profile = SoftwareProfile(workspace=tmp_path, acceptance_commands=["true"])
    controller = ScriptedController([
        Decision("tool", {"tool": "shell", "args": {"command": "printf 72"}}),
        Decision("complete", {"reason": "done"}),
    ])
    state = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller,
        run_dir=tmp_path / "run",
        workspace=tmp_path,
        budget=Budget(hard_max_steps=3),
    ).run()
    assert state.facts == {}
    assert state.observations
