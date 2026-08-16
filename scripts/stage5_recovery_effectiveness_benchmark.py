from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.budget import Budget
from harness.core.controller import Decision
from harness.core.contracts import GoalContract
from harness.core.failures import FailureRouter, RecoveryAction
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.core.security import SecurityConfig
from harness.core.tools import SideEffect, ToolSpec
from harness.profiles.base import DomainProfile


RECOVERABLE_SCENARIOS = ("tool_repair", "missing_info_observe", "verification_replan")
ALL_SCENARIOS = RECOVERABLE_SCENARIOS + ("terminal_security",)


class NoAutomaticRecoveryRouter(FailureRouter):
    """Benchmark baseline: preserve terminal safety, stop on first nonterminal failure."""

    def route(self, failure, repeat_count: int = 1):
        if failure.kind in self.TERMINAL_KINDS:
            return super().route(failure, repeat_count)
        return RecoveryAction.CHECKPOINT_STOP

    def descriptor(self):
        data = super().descriptor()
        data["benchmark_mode"] = "no_automatic_recovery_fail_closed"
        return data


class BenchmarkProfile(DomainProfile):
    name = "stage5-recovery-effectiveness-benchmark"

    def __init__(self, workspace: Path, scenario: str, counters: dict[str, int]):
        self.workspace = Path(workspace)
        self.scenario = scenario
        self.counters = counters

    def default_goal(self):
        return GoalContract(
            goal=f"complete deterministic recovery benchmark scenario {self.scenario}",
            acceptance=["completion oracle observes the scenario-specific solved tool result"],
            constraints=["same controller/tools/oracle/budget in both A/B arms"],
            pinned_constraints=["recovery itself may not execute tools or mutate verified facts"],
            task_id=f"stage5-effectiveness-{self.scenario}",
        )

    def tools(self):
        counters = self.counters
        scenario = self.scenario

        def primary():
            counters["primary"] += 1
            raise RuntimeError(f"injected primary failure:{scenario}")

        def observe():
            counters["observe"] += 1
            return {"observed": True, "scenario": scenario, "token": "deterministic-info"}

        def alternate():
            counters["alternate"] += 1
            return {"solved": True, "scenario": scenario, "path": "alternate"}

        def unsafe_write():
            # Strict isolation must reject this generic WRITE handler before it runs.
            counters["unsafe_handler"] += 1
            return {"unsafe_executed": True}

        return {
            "primary": ToolSpec(
                "primary", "Injected failing primary path", primary,
                side_effect=SideEffect.NONE,
            ),
            "observe": ToolSpec(
                "observe", "Gather deterministic missing information", observe,
                side_effect=SideEffect.READ,
            ),
            "alternate": ToolSpec(
                "alternate", "Deterministic alternate successful path", alternate,
                side_effect=SideEffect.NONE,
            ),
            "unsafe_write": ToolSpec(
                "unsafe_write", "Generic write tool intentionally rejected in strict isolation", unsafe_write,
                side_effect=SideEffect.WRITE,
                idempotent=False,
            ),
        }

    def completion_oracle(self):
        scenario = self.scenario

        def accept(*, state, **_):
            solved = any(
                observation.source == "alternate"
                and observation.ok
                and isinstance(observation.preview, dict)
                and observation.preview.get("solved") is True
                and observation.preview.get("scenario") == scenario
                for observation in state.observations
            )
            return CompletionResult(
                solved,
                "scenario solved by accepted alternate observation" if solved else "scenario not solved",
                evidence=[{"scenario": scenario, "solved": solved}],
                coverage={"scenario": scenario},
            )

        return PredicateCompletionOracle(
            accept,
            name=f"stage5-effectiveness-oracle:{scenario}",
        )


class BenchmarkController:
    """One deterministic policy used unchanged in both benchmark arms."""

    def __init__(self, scenario: str):
        self.scenario = scenario

    @staticmethod
    def _successful_source(state, source: str) -> bool:
        return any(obs.source == source and obs.ok for obs in state.observations)

    def decide(self, goal, state, context):
        del goal
        directive = context.get("recovery_directive")

        if self.scenario == "terminal_security":
            return Decision("tool", {"tool": "unsafe_write", "args": {}})

        if self._successful_source(state, "alternate"):
            return Decision("complete", {"reason": "alternate path produced oracle evidence"})

        if directive is not None:
            action = directive.get("action")
            if action == RecoveryAction.OBSERVE.value:
                return Decision("tool", {"tool": "observe", "args": {}})
            if action in {
                RecoveryAction.REPAIR.value,
                RecoveryAction.REPLAN.value,
                RecoveryAction.ROLLBACK.value,
                RecoveryAction.SWITCH_STRATEGY.value,
                RecoveryAction.RETRY.value,
            }:
                return Decision("tool", {"tool": "alternate", "args": {}})

        if self.scenario == "tool_repair":
            return Decision("tool", {"tool": "primary", "args": {}})

        if self.scenario == "missing_info_observe":
            if self._successful_source(state, "observe"):
                return Decision("tool", {"tool": "alternate", "args": {}})
            return Decision("verify_claim", {"key": "missing-required-claim"})

        if self.scenario == "verification_replan":
            # The first completion request is intentionally premature. The same
            # oracle rejects it in both arms; only routing policy differs after.
            return Decision("complete", {"reason": "premature initial completion attempt"})

        raise RuntimeError(f"unknown benchmark scenario: {self.scenario}")


def _events(runtime: HarnessRuntime):
    return runtime.events.verify_chain()


def _actor_guarded_tools(runtime: HarnessRuntime) -> bool:
    """Every tool.result after a recovery transition must be preceded by a later Actor decision."""
    records = _events(runtime)
    last_recovery_seq = -1
    last_decision_seq = -1
    for record in records:
        seq = int(record["seq"])
        kind = record["kind"]
        if kind == "recovery.transition":
            last_recovery_seq = seq
        elif kind == "decision":
            last_decision_seq = seq
        elif kind == "tool.result" and last_recovery_seq >= 0:
            if last_decision_seq <= last_recovery_seq:
                return False
    return True


def run_arm(root: Path, scenario: str, arm: str) -> dict:
    workspace = root / f"{scenario}-{arm}-workspace"
    workspace.mkdir()
    counters = {"primary": 0, "observe": 0, "alternate": 0, "unsafe_handler": 0}
    profile = BenchmarkProfile(workspace, scenario, counters)
    router = FailureRouter() if arm == "recovery" else NoAutomaticRecoveryRouter()
    strict = scenario == "terminal_security"
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=BenchmarkController(scenario),
        run_dir=root / f"{scenario}-{arm}-run",
        workspace=workspace,
        budget=Budget(hard_max_steps=12),
        failure_router=router,
        security_config=SecurityConfig(strict_tool_isolation=strict),
        task_revision=f"stage5-effectiveness-{scenario}-v1",
    )
    state = runtime.run()
    records = _events(runtime)
    decisions = sum(1 for record in records if record["kind"] == "decision")
    max_repeat = max((int(item.get("repeat_count", 0)) for item in state.failures), default=0)
    unsafe_retries = sum(
        1
        for transition in state.recovery_history
        if transition.action == RecoveryAction.RETRY and not transition.retry_safe
    )
    return {
        "scenario": scenario,
        "arm": arm,
        "completed": bool(state.completed),
        "halted": bool(runtime.halted),
        "steps": int(state.step),
        "actor_decisions": decisions,
        "tool_calls": int(runtime.metrics["tool_calls"]),
        "failures": int(runtime.metrics["failures"]),
        "recovery_transitions": int(runtime.metrics["recovery_transitions"]),
        "strategy_switches": int(runtime.metrics["strategy_switches"]),
        "oracle_checks": int(runtime.metrics["oracle_checks"]),
        "max_repeat_count": max_repeat,
        "unsafe_retries": unsafe_retries,
        "verified_fact_count": len(state.facts),
        "tool_calls_actor_guarded": _actor_guarded_tools(runtime),
        "counters": counters,
        "failure_kinds": [item["kind"] for item in state.failures],
        "recovery_actions": [transition.action.value for transition in state.recovery_history],
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vsh-stage5-effectiveness-") as td:
        root = Path(td)
        pairs = {}
        for scenario in ALL_SCENARIOS:
            pairs[scenario] = {
                "recovery": run_arm(root, scenario, "recovery"),
                "no_recovery": run_arm(root, scenario, "no_recovery"),
            }

        recoverable_recovery_success = sum(
            1 for scenario in RECOVERABLE_SCENARIOS if pairs[scenario]["recovery"]["completed"]
        )
        recoverable_baseline_success = sum(
            1 for scenario in RECOVERABLE_SCENARIOS if pairs[scenario]["no_recovery"]["completed"]
        )
        recovered_pairs = [
            scenario for scenario in RECOVERABLE_SCENARIOS
            if pairs[scenario]["recovery"]["completed"]
            and not pairs[scenario]["no_recovery"]["completed"]
        ]
        extra_steps = sum(
            pairs[s]["recovery"]["steps"] - pairs[s]["no_recovery"]["steps"]
            for s in recovered_pairs
        )
        extra_tools = sum(
            pairs[s]["recovery"]["tool_calls"] - pairs[s]["no_recovery"]["tool_calls"]
            for s in recovered_pairs
        )

        safety = pairs["terminal_security"]
        safety_pass = (
            not safety["recovery"]["completed"]
            and safety["recovery"]["halted"]
            and not safety["no_recovery"]["completed"]
            and safety["no_recovery"]["halted"]
            and safety["recovery"]["counters"]["unsafe_handler"] == 0
            and safety["no_recovery"]["counters"]["unsafe_handler"] == 0
        )
        control_integrity = all(
            pair[arm]["verified_fact_count"] == 0
            and pair[arm]["unsafe_retries"] == 0
            and pair[arm]["tool_calls_actor_guarded"]
            for pair in pairs.values()
            for arm in ("recovery", "no_recovery")
        )

        recovery_rate = recoverable_recovery_success / len(RECOVERABLE_SCENARIOS)
        baseline_rate = recoverable_baseline_success / len(RECOVERABLE_SCENARIOS)
        summary = {
            "benchmark": "stage5-recovery-effectiveness-ab-v1",
            "recoverable_scenarios": len(RECOVERABLE_SCENARIOS),
            "recovery_completion_rate": recovery_rate,
            "no_recovery_completion_rate": baseline_rate,
            "completion_rate_delta": recovery_rate - baseline_rate,
            "recovered_pair_count": len(recovered_pairs),
            "recovered_pairs": recovered_pairs,
            "additional_steps_total": extra_steps,
            "additional_tool_calls_total": extra_tools,
            "additional_steps_per_recovered_success": (
                extra_steps / len(recovered_pairs) if recovered_pairs else None
            ),
            "additional_tool_calls_per_recovered_success": (
                extra_tools / len(recovered_pairs) if recovered_pairs else None
            ),
            "terminal_safety_pass": safety_pass,
            "control_integrity_pass": control_integrity,
            "safety_regressions": 0 if safety_pass else 1,
        }
        summary["all_passed"] = (
            recoverable_recovery_success > recoverable_baseline_success
            and len(recovered_pairs) >= 3
            and safety_pass
            and control_integrity
        )

        payload = {"pairs": pairs, "summary": summary}
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
