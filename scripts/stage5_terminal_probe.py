from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision
from harness.core.failures import FailureKind, RecoveryAction, RecoveryStatus
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.core.tools import SideEffect, ToolSpec
from harness.profiles.base import DomainProfile


class TerminalProbeProfile(DomainProfile):
    name = "stage5-terminal-probe"

    def __init__(self, workspace: Path, effect_file: Path, mode: str):
        self.workspace = workspace
        self.effect_file = effect_file
        self.mode = mode
        self.handler_calls = 0

    def default_goal(self):
        return GoalContract(goal="probe terminal recovery", acceptance=["external oracle"])

    def tools(self):
        profile = self
        if self.mode == "fail":
            def handler():
                profile.handler_calls += 1
                raise RuntimeError("repeatable failure")

            return {
                "external": ToolSpec(
                    name="external", description="failing tool", handler=handler,
                    side_effect=SideEffect.NONE, idempotent=True,
                    provenance={"revision": "stage5-terminal-probe-fail-v1"},
                )
            }

        effect_file = self.effect_file

        def handler(value: str):
            profile.handler_calls += 1
            effect_file.write_text(value, encoding="utf-8")
            return value

        return {
            "external": ToolSpec(
                name="external", description="external effect", handler=handler,
                side_effect=SideEffect.EXTERNAL, idempotent=False,
                provenance={"revision": "stage5-terminal-probe-external-v1"},
            )
        }

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(False, "not complete"),
            name="stage5-terminal-probe-oracle",
        )


class ToolController:
    def __init__(self, args):
        self.args = dict(args)
        self.calls = 0

    def decide(self, goal, state, context):
        self.calls += 1
        return Decision("tool", {"tool": "external", "args": dict(self.args)})


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vsh-stage5-terminal-") as td:
        root = Path(td)
        outcomes = {}

        workspace = root / "ambiguous-workspace"
        workspace.mkdir()
        effect_file = root / "ambiguous-effect.txt"
        profile = TerminalProbeProfile(workspace, effect_file, "external")
        controller = ToolController({"value": "ONCE"})
        runtime = HarnessRuntime(
            goal=profile.default_goal(), profile=profile, controller=controller,
            run_dir=root / "ambiguous-run", workspace=workspace,
            budget=Budget(hard_max_steps=5), task_revision="stage5-terminal-probe-ambiguous-v1",
        )
        action_id = runtime.receipts.action_id(
            run_id=runtime.run_id, step=0, tool="external", args={"value": "ONCE"}
        )
        runtime.receipts.prepare(
            action_id=action_id, run_id=runtime.run_id, step=0,
            tool="external", args={"value": "ONCE"},
        )
        ambiguous_state = runtime.run()
        terminal = ambiguous_state.recovery_history[-1]
        outcomes["prepared_receipt_terminalized"] = {
            "passed": (
                runtime.halted
                and ambiguous_state.recovery_halted
                and ambiguous_state.pending_recovery is None
                and terminal.action == RecoveryAction.CHECKPOINT_STOP
                and terminal.failure_kind == FailureKind.PERSISTENCE_ERROR
                and terminal.status == RecoveryStatus.APPLIED
                and profile.handler_calls == 0
                and not effect_file.exists()
            ),
            "runtime_halted": runtime.halted,
            "recovery_halted": ambiguous_state.recovery_halted,
            "pending_recovery": ambiguous_state.pending_recovery is not None,
            "terminal_action": terminal.action.value,
            "handler_calls": profile.handler_calls,
            "effect_exists": effect_file.exists(),
        }

        workspace2 = root / "supersede-workspace"
        workspace2.mkdir()
        profile2 = TerminalProbeProfile(workspace2, root / "unused.txt", "fail")
        controller2 = ToolController({})
        runtime2 = HarnessRuntime(
            goal=profile2.default_goal(), profile=profile2, controller=controller2,
            run_dir=root / "supersede-run", workspace=workspace2,
            budget=Budget(hard_max_steps=1), task_revision="stage5-terminal-probe-supersede-v1",
        )
        supersede_state = runtime2.run()
        prior = supersede_state.recovery_history[-2]
        final = supersede_state.recovery_history[-1]
        outcomes["budget_supersedes_pending_repair"] = {
            "passed": (
                runtime2.halted
                and supersede_state.step == 1
                and controller2.calls == 1
                and profile2.handler_calls == 1
                and prior.action == RecoveryAction.REPAIR
                and prior.status == RecoveryStatus.SUPERSEDED
                and final.action == RecoveryAction.CHECKPOINT_STOP
                and final.failure_kind == FailureKind.BUDGET_EXCEEDED
                and final.status == RecoveryStatus.APPLIED
                and final.details.get("step_consumed") is False
            ),
            "persisted_step": supersede_state.step,
            "controller_calls": controller2.calls,
            "handler_calls": profile2.handler_calls,
            "superseded_action": prior.action.value,
            "superseded_status": prior.status.value,
            "terminal_action": final.action.value,
            "terminal_failure": final.failure_kind.value,
            "terminal_step_consumed": final.details.get("step_consumed"),
        }

        all_passed = all(item["passed"] for item in outcomes.values())
        result = {
            "stage": "05",
            "probe": "terminal-rc4",
            "outcomes": outcomes,
            "summary": {
                "all_passed": all_passed,
                "scenario_count": len(outcomes),
                "ambiguous_effect_executions": 1 if effect_file.exists() else 0,
                "pending_terminal_transitions": sum(
                    1 for item in outcomes.values()
                    if item.get("pending_recovery") is True
                ),
                "budget_step_overshoot": max(0, supersede_state.step - 1),
            },
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
