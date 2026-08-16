from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.core.storage import IntegrityError, ResumeConflict, canonical_hash
from harness.core.tools import SideEffect, ToolSpec
from harness.profiles.base import DomainProfile
from harness.profiles.demo import DemoProfile


class StepController:
    def decide(self, goal, state, context):
        if state.step == 0:
            return Decision("propose", {"key": "demo.started", "value": True})
        if state.step == 1:
            return Decision("verify_claim", {"key": "demo.started"})
        return Decision("complete", {"reason": "done"})


class ForcedProfile(DomainProfile):
    name = "stage3-forced-effect"

    def __init__(self, effect_file: str | Path):
        self.effect_file = Path(effect_file)

    def default_goal(self):
        return GoalContract(goal="execute one durable side effect", acceptance=["oracle accepts"])

    def tools(self):
        effect_file = self.effect_file

        def external_effect(value: str):
            with effect_file.open("a", encoding="utf-8") as handle:
                handle.write(value + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return {"written": value}

        return {
            "external": ToolSpec(
                name="external",
                description="probe non-idempotent external effect",
                handler=external_effect,
                side_effect=SideEffect.EXTERNAL,
                idempotent=False,
                provenance={"kind": "stage3-probe", "revision": "v1"},
            )
        }

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(True, "probe oracle accepted"),
            name="stage3_probe_oracle",
        )


class ForcedController:
    def decide(self, goal, state, context):
        if state.step == 0:
            return Decision("tool", {"tool": "external", "args": {"value": "ONCE"}})
        if os.getenv("VSH_STAGE3_FORCE_KILL") == "1":
            os._exit(73)
        return Decision("complete", {"reason": "resumed"})


def _demo_runtime(root: Path, name: str, *, resume=False):
    workspace = root / f"{name}-workspace"
    workspace.mkdir(exist_ok=True)
    profile = DemoProfile()
    kwargs = dict(
        goal=profile.default_goal(),
        profile=profile,
        controller=StepController(),
        run_dir=root / name,
        workspace=workspace,
        task_revision="stage3-probe-demo-v1",
        budget=Budget(hard_max_steps=10),
    )
    return HarnessRuntime.resume(**kwargs) if resume else HarnessRuntime(**kwargs)


def child_mode(args) -> int:
    profile = ForcedProfile(args.effect_file)
    HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ForcedController(),
        run_dir=Path(args.run_dir),
        workspace=Path(args.workspace),
        task_revision="stage3-forced-v1",
        budget=Budget(hard_max_steps=5),
    ).run()
    return 0


def run_probe() -> dict:
    with tempfile.TemporaryDirectory(prefix="vsh-stage3-probe-") as tmp:
        root = Path(tmp)
        results: dict[str, dict] = {}

        # Canonical event replay and checkpoint anchor.
        runtime = _demo_runtime(root, "replay")
        state = runtime.run()
        cp = runtime.checkpoints.load_verified()
        replay_hash = runtime.replay_state_hash()
        results["deterministic_replay"] = {
            "passed": replay_hash == canonical_hash(state.snapshot()) == cp["state_hash"],
            "state_hash": replay_hash,
            "event_seq": cp["event_seq"],
        }

        # Corrupted/truncated checkpoint must fail closed.
        runtime = _demo_runtime(root, "corrupt")
        runtime.run()
        cp_path = root / "corrupt" / "checkpoint.json"
        cp_path.write_text('{"body":', encoding="utf-8")
        detected = False
        reason = ""
        try:
            _demo_runtime(root, "corrupt", resume=True)
        except IntegrityError as exc:
            detected = True
            reason = str(exc)
        results["checkpoint_corruption"] = {"passed": detected, "reason": reason}

        # Forced process exit after a persisted transition, then resume.
        forced_run = root / "forced-run"
        forced_workspace = root / "forced-workspace"
        effect_file = root / "forced-effects.txt"
        forced_workspace.mkdir()
        env = dict(os.environ)
        env["VSH_STAGE3_FORCE_KILL"] = "1"
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        child = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--child",
                "--run-dir", str(forced_run),
                "--workspace", str(forced_workspace),
                "--effect-file", str(effect_file),
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        profile = ForcedProfile(effect_file)
        resumed = HarnessRuntime.resume(
            goal=profile.default_goal(),
            profile=profile,
            controller=ForcedController(),
            run_dir=forced_run,
            workspace=forced_workspace,
            task_revision="stage3-forced-v1",
            budget=Budget(hard_max_steps=5),
        )
        resumed_state = resumed.run()
        effects = effect_file.read_text(encoding="utf-8").splitlines()
        results["forced_kill_resume"] = {
            "passed": child.returncode == 73 and resumed_state.completed and effects == ["ONCE"],
            "child_returncode": child.returncode,
            "effects": effects,
            "duplicate_external_actions": max(0, len(effects) - 1),
            "restored_run_id": resumed.run_id,
        }

        # PREPARED without COMMITTED is the unavoidable ambiguous crash window.
        ambiguous_run = root / "ambiguous-run"
        ambiguous_workspace = root / "ambiguous-workspace"
        ambiguous_effect = root / "ambiguous-effects.txt"
        ambiguous_workspace.mkdir()
        profile = ForcedProfile(ambiguous_effect)
        pending = HarnessRuntime(
            goal=profile.default_goal(),
            profile=profile,
            controller=ForcedController(),
            run_dir=ambiguous_run,
            workspace=ambiguous_workspace,
            task_revision="stage3-forced-v1",
            budget=Budget(hard_max_steps=5),
        )
        action_id = pending.receipts.action_id(
            run_id=pending.run_id,
            step=0,
            tool="external",
            args={"value": "ONCE"},
        )
        pending.receipts.prepare(
            action_id=action_id,
            run_id=pending.run_id,
            step=0,
            tool="external",
            args={"value": "ONCE"},
        )
        pending.log("run.start", {"run_id": pending.run_id, "manifest_hash": pending.manifest_hash})
        pending._persist_state("run.start")
        resumed_pending = HarnessRuntime.resume(
            goal=profile.default_goal(),
            profile=profile,
            controller=ForcedController(),
            run_dir=ambiguous_run,
            workspace=ambiguous_workspace,
            task_revision="stage3-forced-v1",
            budget=Budget(hard_max_steps=5),
        )
        pending_state = resumed_pending.run()
        results["ambiguous_side_effect_fail_closed"] = {
            "passed": resumed_pending.halted and not pending_state.completed and not ambiguous_effect.exists(),
            "halted": resumed_pending.halted,
            "effect_executed": ambiguous_effect.exists(),
            "ambiguous_side_effects": resumed_pending.metrics["ambiguous_side_effects"],
        }

        summary = {
            "all_passed": all(item.get("passed") for item in results.values()),
            "probe_count": len(results),
            "passed_count": sum(1 for item in results.values() if item.get("passed")),
            "duplicate_external_actions": results["forced_kill_resume"]["duplicate_external_actions"],
        }
        return {"probe_version": "stage3-v0.4.0", "results": results, "summary": summary}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--run-dir")
    parser.add_argument("--workspace")
    parser.add_argument("--effect-file")
    args = parser.parse_args()
    if args.child:
        return child_mode(args)
    result = run_probe()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
