from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from harness.core.budget import Budget
from harness.core.controller import Decision
from harness.core.events import EventLog
from harness.core.runtime import HarnessRuntime
from harness.core.security import SecurityConfig
from harness.core.storage import (
    IntegrityError,
    PersistenceError,
    ResumeConflict,
    RunManifestStore,
    canonical_hash,
)
from harness.core.tools import SideEffect, ToolSpec
from harness.profiles.base import DomainProfile
from harness.profiles.demo import DemoProfile
from harness.core.oracles import PredicateCompletionOracle, CompletionResult


class StepController:
    def decide(self, goal, state, context):
        if state.step == 0:
            return Decision("propose", {"key": "demo.started", "value": True})
        if state.step == 1:
            return Decision("verify_claim", {"key": "demo.started"})
        return Decision("complete", {"reason": "done"})


def make_demo(tmp_path: Path, *, run_name="run", task_revision="task-v1", resume=False):
    kwargs = dict(
        goal=DemoProfile().default_goal(),
        profile=DemoProfile(),
        controller=StepController(),
        run_dir=tmp_path / run_name,
        workspace=tmp_path / "workspace",
        budget=Budget(hard_max_steps=10),
        task_revision=task_revision,
    )
    (tmp_path / "workspace").mkdir(exist_ok=True)
    return HarnessRuntime.resume(**kwargs) if resume else HarnessRuntime(**kwargs)


def test_manifest_checkpoint_and_event_chain_are_integrity_bound(tmp_path):
    runtime = make_demo(tmp_path)
    state = runtime.run()
    assert state.completed

    manifest, manifest_hash = RunManifestStore(tmp_path / "run" / "run_manifest.json").load_verified()
    checkpoint = runtime.checkpoints.load_verified()
    assert manifest["run_id"] == runtime.run_id
    assert checkpoint["manifest_hash"] == manifest_hash
    assert checkpoint["state_hash"] == canonical_hash(state.snapshot())
    anchor = runtime.events.record_at(checkpoint["event_seq"])
    assert anchor["record_hash"] == checkpoint["event_hash"]
    assert anchor["kind"] == "state.snapshot"
    assert runtime.replay_state_hash() == checkpoint["state_hash"]


def test_corrupted_checkpoint_fails_closed(tmp_path):
    runtime = make_demo(tmp_path)
    runtime.run()
    checkpoint_path = tmp_path / "run" / "checkpoint.json"
    checkpoint_path.write_text('{"body":', encoding="utf-8")
    with pytest.raises(IntegrityError):
        make_demo(tmp_path, resume=True)


def test_checkpoint_event_anchor_mismatch_fails_closed(tmp_path):
    runtime = make_demo(tmp_path)
    runtime.run()
    path = tmp_path / "run" / "checkpoint.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["body"]["event_hash"] = "f" * 64
    # Re-seal the checkpoint so the failure specifically exercises the event anchor.
    raw["integrity"]["sha256"] = canonical_hash(raw["body"])
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(IntegrityError, match="event anchor"):
        make_demo(tmp_path, resume=True)


def test_resume_rejects_config_or_task_revision_drift(tmp_path):
    runtime = make_demo(tmp_path)
    runtime.run()
    with pytest.raises(ResumeConflict, match="task revision"):
        make_demo(tmp_path, task_revision="task-v2", resume=True)

    profile = DemoProfile()
    from dataclasses import replace
    altered_goal = replace(profile.default_goal(), goal="different goal")
    with pytest.raises(ResumeConflict, match="configuration"):
        HarnessRuntime.resume(
            goal=altered_goal,
            profile=profile,
            controller=StepController(),
            run_dir=tmp_path / "run",
            workspace=tmp_path / "workspace",
            task_revision="task-v1",
        )


def test_event_log_payload_tampering_breaks_hash_chain(tmp_path):
    runtime = make_demo(tmp_path)
    runtime.run()
    path = tmp_path / "run" / "events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["payload"]["reason"] = "tampered"
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(IntegrityError, match="hash mismatch"):
        EventLog(path)


def test_missing_provenance_warns_and_strict_mode_fails(tmp_path):
    (tmp_path / "workspace").mkdir()
    profile = DemoProfile()
    runtime = HarnessRuntime(
        goal=profile.default_goal(), profile=profile, controller=StepController(),
        run_dir=tmp_path / "warn-run", workspace=tmp_path / "workspace",
    )
    assert "task_revision is unspecified" in runtime.manifest_body["provenance_warnings"]
    assert runtime.manifest_body["provenance_complete"] is False

    with pytest.raises(PersistenceError, match="incomplete run provenance"):
        HarnessRuntime(
            goal=profile.default_goal(), profile=profile, controller=StepController(),
            run_dir=tmp_path / "strict-run", workspace=tmp_path / "workspace",
            require_complete_provenance=True,
        )


class EffectProfile(DomainProfile):
    name = "effect-test"

    def __init__(self, counter: Path):
        self.counter = counter

    def default_goal(self):
        from harness.core.contracts import GoalContract
        return GoalContract(goal="one effect", acceptance=["done"])

    def tools(self):
        counter = self.counter
        def external(value: str):
            with counter.open("a", encoding="utf-8") as handle:
                handle.write(value + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return {"written": value}
        return {
            "external": ToolSpec(
                name="external", description="non-idempotent effect", handler=external,
                side_effect=SideEffect.EXTERNAL, idempotent=False,
                provenance={"kind": "test", "revision": "v1"},
            )
        }

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(True, "test complete"), name="effect_oracle"
        )


class EffectController:
    def decide(self, goal, state, context):
        if state.step == 0:
            return Decision("tool", {"tool": "external", "args": {"value": "EFFECT"}})
        return Decision("complete", {"reason": "done"})


def effect_runtime(tmp_path, *, resume=False, runtime_cls=HarnessRuntime):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    profile = EffectProfile(tmp_path / "effects.txt")
    kwargs = dict(
        goal=profile.default_goal(), profile=profile, controller=EffectController(),
        run_dir=tmp_path / "run", workspace=workspace,
        budget=Budget(hard_max_steps=5), task_revision="effect-task-v1",
        security_config=SecurityConfig(),
    )
    if resume:
        return runtime_cls.resume(**kwargs)
    return runtime_cls(**kwargs)


def test_committed_receipt_is_deduplicated_if_checkpoint_lags(tmp_path):
    class CrashBeforeTransition(HarnessRuntime):
        def _persist_state(self, reason):
            if reason == "step.transition" and self.state.step == 1:
                raise RuntimeError("simulated crash after receipt commit")
            return super()._persist_state(reason)

    runtime = effect_runtime(tmp_path, runtime_cls=CrashBeforeTransition)
    with pytest.raises(RuntimeError, match="simulated crash"):
        runtime.run()
    assert (tmp_path / "effects.txt").read_text().splitlines() == ["EFFECT"]

    resumed = effect_runtime(tmp_path, resume=True)
    state = resumed.run()
    assert state.completed
    assert (tmp_path / "effects.txt").read_text().splitlines() == ["EFFECT"]
    assert resumed.metrics["receipt_deduplications"] == 1


def test_prepared_only_receipt_blocks_automatic_reexecution(tmp_path):
    runtime = effect_runtime(tmp_path)
    action_id = runtime.receipts.action_id(
        run_id=runtime.run_id, step=0, tool="external", args={"value": "EFFECT"}
    )
    runtime.receipts.prepare(
        action_id=action_id, run_id=runtime.run_id, step=0,
        tool="external", args={"value": "EFFECT"},
    )
    # Create the initial durable checkpoint without executing the action.
    runtime.log("run.start", {"run_id": runtime.run_id, "manifest_hash": runtime.manifest_hash})
    runtime._persist_state("run.start")

    resumed = effect_runtime(tmp_path, resume=True)
    state = resumed.run()
    assert not state.completed
    assert resumed.halted
    assert resumed.metrics["ambiguous_side_effects"] == 1
    assert not (tmp_path / "effects.txt").exists()
    assert any(f["kind"] == "persistence_error" for f in state.failures)


def test_real_forced_process_exit_resumes_without_duplicate_effect(tmp_path):
    project = Path(__file__).resolve().parents[1]
    run_dir = tmp_path / "forced-run"
    workspace = tmp_path / "forced-workspace"
    effects = tmp_path / "forced-effects.txt"
    workspace.mkdir()

    fixture = tmp_path / "forced_fixture.py"
    fixture.write_text(textwrap.dedent(r'''
        import os
        from pathlib import Path
        from harness.core.controller import Decision
        from harness.core.contracts import GoalContract
        from harness.core.tools import ToolSpec, SideEffect
        from harness.core.oracles import PredicateCompletionOracle, CompletionResult
        from harness.profiles.base import DomainProfile

        class P(DomainProfile):
            name = "forced-effect"
            def __init__(self, effects): self.effects = Path(effects)
            def default_goal(self): return GoalContract(goal="forced", acceptance=["done"])
            def tools(self):
                effects = self.effects
                def effect():
                    with effects.open("a", encoding="utf-8") as f:
                        f.write("ONCE\n"); f.flush(); os.fsync(f.fileno())
                    return "ok"
                return {"effect": ToolSpec(name="effect", description="x", handler=effect, side_effect=SideEffect.EXTERNAL, idempotent=False, provenance={"revision":"v1"})}
            def completion_oracle(self):
                return PredicateCompletionOracle(lambda **_: CompletionResult(True,"ok"), name="o")

        class C:
            def decide(self, goal, state, context):
                if state.step == 0:
                    return Decision("tool", {"tool":"effect","args":{}})
                if os.getenv("FORCED_KILL") == "1":
                    os._exit(73)
                return Decision("complete", {"reason":"resume"})
    '''), encoding="utf-8")

    child = tmp_path / "forced_child.py"
    child.write_text(textwrap.dedent(f'''\
        from pathlib import Path
        from harness.core.runtime import HarnessRuntime
        from forced_fixture import P, C
        p=P(Path({str(effects)!r}))
        HarnessRuntime(goal=p.default_goal(), profile=p, controller=C(), run_dir=Path({str(run_dir)!r}), workspace=Path({str(workspace)!r}), task_revision="forced-v1").run()
    '''), encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(project / "src"), str(tmp_path)])
    env["FORCED_KILL"] = "1"
    result = subprocess.run([sys.executable, str(child)], env=env, cwd=project)
    assert result.returncode == 73
    assert effects.read_text().splitlines() == ["ONCE"]

    sys.path.insert(0, str(tmp_path))
    try:
        import importlib
        forced_fixture = importlib.import_module("forced_fixture")
        p = forced_fixture.P(effects)
        resumed = HarnessRuntime.resume(
            goal=p.default_goal(), profile=p, controller=forced_fixture.C(), run_dir=run_dir,
            workspace=workspace, task_revision="forced-v1",
        )
        state = resumed.run()
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("forced_fixture", None)
    assert state.completed
    assert effects.read_text().splitlines() == ["ONCE"]
    assert resumed.run_id == resumed.manifest_body["run_id"]

def test_event_ahead_of_checkpoint_recovers_latest_verified_snapshot(tmp_path):
    runtime = make_demo(tmp_path)
    runtime.run()
    old_checkpoint = runtime.checkpoints.load_verified()
    snapshot = runtime.state.snapshot()
    snapshot["unknowns"] = ["event-ahead-recovered"]
    snapshot["step"] = int(snapshot["step"]) + 1
    state_hash = canonical_hash(snapshot)
    record = runtime.events.append_event(
        __import__("harness.core.events", fromlist=["Event"]).Event(
            "state.snapshot",
            {
                "reason": "simulated-crash-before-checkpoint",
                "state_hash": state_hash,
                "state": snapshot,
                "manifest_hash": runtime.manifest_hash,
                "runtime_meta": runtime._runtime_meta(),
            },
            snapshot["step"],
        )
    )
    assert record["seq"] > old_checkpoint["event_seq"]

    resumed = make_demo(tmp_path, resume=True)
    assert resumed.state.unknowns == ["event-ahead-recovered"]
    new_checkpoint = resumed.checkpoints.load_verified()
    assert new_checkpoint["event_seq"] == record["seq"]
    assert new_checkpoint["state_hash"] == state_hash


def test_resume_rejects_budget_drift_and_new_run_rejects_dirty_directory(tmp_path):
    runtime = make_demo(tmp_path)
    runtime.run()
    profile = DemoProfile()
    with pytest.raises(ResumeConflict, match="configuration"):
        HarnessRuntime.resume(
            goal=profile.default_goal(), profile=profile, controller=StepController(),
            run_dir=tmp_path / "run", workspace=tmp_path / "workspace",
            budget=Budget(hard_max_steps=11), task_revision="task-v1",
        )

    dirty = tmp_path / "dirty"
    dirty.mkdir()
    (dirty / "stale.txt").write_text("stale", encoding="utf-8")
    with pytest.raises(ResumeConflict, match="not empty"):
        HarnessRuntime(
            goal=profile.default_goal(), profile=profile, controller=StepController(),
            run_dir=dirty, workspace=tmp_path / "workspace", task_revision="task-v1",
        )


def test_cli_exposes_public_resume_entry_point(tmp_path):
    project = Path(__file__).resolve().parents[1]
    run_dir = tmp_path / "cli-run"
    workspace = tmp_path / "cli-workspace"
    workspace.mkdir()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project / "src")
    base = [
        sys.executable, "-m", "harness.cli", "--profile", "demo",
        "--run-dir", str(run_dir), "--workspace", str(workspace),
        "--task-revision", "cli-demo-v1",
    ]
    first = subprocess.run(base, cwd=project, env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    manifest_before, _ = RunManifestStore(run_dir / "run_manifest.json").load_verified()
    second = subprocess.run(base + ["--resume"], cwd=project, env=env, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    manifest_after, _ = RunManifestStore(run_dir / "run_manifest.json").load_verified()
    assert manifest_after["run_id"] == manifest_before["run_id"]
    assert "completed=True" in second.stdout
