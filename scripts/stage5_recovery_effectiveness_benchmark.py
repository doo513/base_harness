from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from harness.core.budget import Budget
from harness.core.controller import Decision
from harness.core.contracts import GoalContract
from harness.core.failures import FailureRouter, RecoveryAction
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.progress import ProgressPolicy
from harness.core.retrieval import RetrievalPolicy, RetrievalUnavailable
from harness.core.runtime import HarnessRuntime
from harness.core.security import SecurityConfig
from harness.core.tools import SideEffect, ToolSpec
from harness.profiles.base import DomainProfile


ARMS = ("stop", "retry_only", "generic_replan", "typed_targeted")
RECOVERABLE_SCENARIOS = ("tool_repair", "missing_info_observe", "verification_replan")
NEGATIVE_SCENARIOS = (
    "irrecoverable_env_error",
    "strategy_exhausted",
    "oracle_permanent_reject",
    "terminal_security",
)
ALL_SCENARIOS = RECOVERABLE_SCENARIOS + NEGATIVE_SCENARIOS

EXPECTED_TYPED_FIRST_ACTION = {
    "tool_repair": RecoveryAction.REPAIR.value,
    "missing_info_observe": RecoveryAction.OBSERVE.value,
    "verification_replan": RecoveryAction.REPLAN.value,
}


class NoAutomaticRecoveryRouter(FailureRouter):
    """A: preserve terminal safety, stop on the first nonterminal failure."""

    def route(self, failure, repeat_count: int = 1):
        if failure.kind in self.TERMINAL_KINDS:
            return super().route(failure, repeat_count)
        return RecoveryAction.CHECKPOINT_STOP

    def descriptor(self):
        data = super().descriptor()
        data["benchmark_mode"] = "A_no_automatic_recovery_fail_closed"
        return data


class RetryOnlyRouter(FailureRouter):
    """B: retry only when the emitted failure is explicitly marked retry-safe."""

    def route(self, failure, repeat_count: int = 1):
        if failure.kind in self.TERMINAL_KINDS:
            return super().route(failure, repeat_count)
        if repeat_count >= self.repeat_limit:
            return RecoveryAction.CHECKPOINT_STOP
        if failure.retry_safe:
            return RecoveryAction.RETRY
        return RecoveryAction.CHECKPOINT_STOP

    def descriptor(self):
        data = super().descriptor()
        data["benchmark_mode"] = "B_safe_retry_only"
        data["unsafe_retry_policy"] = "checkpoint_stop"
        return data


class GenericFullReplanRouter(FailureRouter):
    """C: collapse every recoverable failure kind to one generic full replan."""

    def route(self, failure, repeat_count: int = 1):
        if failure.kind in self.TERMINAL_KINDS:
            return super().route(failure, repeat_count)
        if repeat_count >= self.repeat_limit:
            return RecoveryAction.SWITCH_STRATEGY
        return RecoveryAction.REPLAN

    def descriptor(self):
        data = super().descriptor()
        data["benchmark_mode"] = "C_generic_full_replan"
        return data


class AlwaysUnavailableRetrievalGateway:
    """Deterministic negative-control gateway: valid descriptor, unavailable search."""

    provider_id = "benchmark_unavailable"
    provider_revision = "benchmark-unavailable-v1"
    index_revision = "benchmark-empty-v1"

    def descriptor(self):
        return {
            "provider_id": self.provider_id,
            "provider_revision": self.provider_revision,
            "index_revision": self.index_revision,
            "ranking_policy_version": RetrievalPolicy.ranking_policy_version,
            "index_hash": hashlib.sha256(b"benchmark-unavailable-empty-index").hexdigest(),
            "item_count": 0,
            "deterministic_replay": True,
            "search_mutates_state": False,
        }

    def search(self, request):
        del request
        raise RetrievalUnavailable("benchmark injected irrecoverable environment outage")


class BenchmarkProfile(DomainProfile):
    name = "stage5-recovery-routing-benchmark"

    def __init__(self, workspace: Path, scenario: str, counters: dict[str, int]):
        self.workspace = Path(workspace)
        self.scenario = scenario
        self.counters = counters

    def default_goal(self):
        return GoalContract(
            goal=f"complete deterministic Stage05 routing benchmark scenario {self.scenario}",
            acceptance=["completion oracle observes scenario-specific solved evidence"],
            constraints=["same controller/tools/oracle/budget across A/B/C/D arms"],
            pinned_constraints=[
                "recovery itself may not execute task tools",
                "negative controls must never be counted as successful recovery",
            ],
            task_id=f"stage5-routing-{self.scenario}",
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
            counters["unsafe_handler"] += 1
            return {"unsafe_executed": True}

        return {
            "primary": ToolSpec(
                "primary",
                "Injected failing primary path",
                primary,
                side_effect=SideEffect.NONE,
            ),
            "observe": ToolSpec(
                "observe",
                "Gather deterministic diagnostic/missing information",
                observe,
                side_effect=SideEffect.READ,
            ),
            "alternate": ToolSpec(
                "alternate",
                "Deterministic alternate successful path",
                alternate,
                side_effect=SideEffect.NONE,
            ),
            "unsafe_write": ToolSpec(
                "unsafe_write",
                "Generic write tool intentionally rejected in strict isolation",
                unsafe_write,
                side_effect=SideEffect.WRITE,
                idempotent=False,
            ),
        }

    def completion_oracle(self):
        scenario = self.scenario

        def accept(*, state, **_):
            if scenario == "oracle_permanent_reject":
                return CompletionResult(
                    False,
                    "benchmark permanent oracle rejection",
                    evidence=[{"scenario": scenario, "accepted": False}],
                    coverage={"scenario": scenario},
                )

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
            name=f"stage5-routing-oracle:{scenario}",
        )


class BenchmarkController:
    """One deterministic Actor policy; it reacts only to kernel recovery directives."""

    def __init__(self, scenario: str):
        self.scenario = scenario

    @staticmethod
    def _successful_source(state, source: str) -> bool:
        return any(obs.source == source and obs.ok for obs in state.observations)

    def _initial_recoverable_failure(self):
        if self.scenario == "tool_repair":
            return Decision("tool", {"tool": "primary", "args": {}})
        if self.scenario == "missing_info_observe":
            return Decision("verify_claim", {"key": "missing-required-claim"})
        if self.scenario == "verification_replan":
            return Decision("complete", {"reason": "premature initial completion attempt"})
        raise RuntimeError(f"not a recoverable scenario: {self.scenario}")

    def decide(self, goal, state, context):
        del goal
        directive = context.get("recovery_directive")
        action = directive.get("action") if directive is not None else None

        if self.scenario == "terminal_security":
            return Decision("tool", {"tool": "unsafe_write", "args": {}})

        if self.scenario == "irrecoverable_env_error":
            if action == RecoveryAction.OBSERVE.value:
                return Decision("tool", {"tool": "observe", "args": {}})
            return Decision("retrieve", {"query": "required environment dependency"})

        if self.scenario == "strategy_exhausted":
            # Deliberately generate activity without recognized progress so the
            # production progress controller must eventually terminally exhaust.
            return Decision("tool", {"tool": "observe", "args": {}})

        if self.scenario == "oracle_permanent_reject":
            if action == RecoveryAction.RETRY.value:
                return Decision("complete", {"reason": "retry permanent oracle"})
            if action in {
                RecoveryAction.REPLAN.value,
                RecoveryAction.SWITCH_STRATEGY.value,
                RecoveryAction.REPAIR.value,
                RecoveryAction.ROLLBACK.value,
            }:
                if not self._successful_source(state, "observe"):
                    return Decision("tool", {"tool": "observe", "args": {}})
                return Decision("tool", {"tool": "alternate", "args": {}})
            if action == RecoveryAction.OBSERVE.value:
                return Decision("tool", {"tool": "observe", "args": {}})
            return Decision("complete", {"reason": "initial permanent oracle attempt"})

        if self.scenario in RECOVERABLE_SCENARIOS:
            if action == RecoveryAction.RETRY.value:
                # Retry-only means repeat the exact failing task action.
                return self._initial_recoverable_failure()

            if action == RecoveryAction.REPAIR.value:
                return Decision("tool", {"tool": "alternate", "args": {}})

            if action == RecoveryAction.OBSERVE.value:
                return Decision("tool", {"tool": "observe", "args": {}})

            if action in {
                RecoveryAction.REPLAN.value,
                RecoveryAction.SWITCH_STRATEGY.value,
                RecoveryAction.ROLLBACK.value,
            }:
                # Generic/full replan pays a deterministic diagnostic step before
                # taking the alternate path. D receives this same behavior for
                # failures whose typed route is itself REPLAN.
                if not self._successful_source(state, "observe"):
                    return Decision("tool", {"tool": "observe", "args": {}})
                return Decision("tool", {"tool": "alternate", "args": {}})

            if self._successful_source(state, "alternate"):
                return Decision("complete", {"reason": "alternate path produced oracle evidence"})

            if self._successful_source(state, "observe"):
                return Decision("tool", {"tool": "alternate", "args": {}})

            return self._initial_recoverable_failure()

        raise RuntimeError(f"unknown benchmark scenario: {self.scenario}")


def _events(runtime: HarnessRuntime):
    return runtime.events.verify_chain()


def _actor_guarded_tools(runtime: HarnessRuntime) -> bool:
    """Every tool.result after recovery must be preceded by a later Actor decision."""
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


def _router_for(arm: str):
    if arm == "stop":
        return NoAutomaticRecoveryRouter()
    if arm == "retry_only":
        return RetryOnlyRouter()
    if arm == "generic_replan":
        return GenericFullReplanRouter()
    if arm == "typed_targeted":
        return FailureRouter()
    raise ValueError(f"unknown arm: {arm}")


def run_arm(root: Path, scenario: str, arm: str) -> dict:
    workspace = root / f"{scenario}-{arm}-workspace"
    workspace.mkdir()
    counters = {"primary": 0, "observe": 0, "alternate": 0, "unsafe_handler": 0}
    profile = BenchmarkProfile(workspace, scenario, counters)

    strict = scenario == "terminal_security"
    retrieval_gateway = None
    retrieval_policy = None
    if scenario == "irrecoverable_env_error":
        retrieval_gateway = AlwaysUnavailableRetrievalGateway()
        retrieval_policy = RetrievalPolicy(enabled=True)

    progress_policy = None
    if scenario == "strategy_exhausted":
        progress_policy = ProgressPolicy(
            family_repeat_limit=2,
            no_progress_streak_limit=4,
            max_strategy_generations_without_progress=1,
        )

    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=BenchmarkController(scenario),
        run_dir=root / f"{scenario}-{arm}-run",
        workspace=workspace,
        budget=Budget(hard_max_steps=24),
        failure_router=_router_for(arm),
        progress_policy=progress_policy,
        security_config=SecurityConfig(strict_tool_isolation=strict),
        retrieval_gateway=retrieval_gateway,
        retrieval_policy=retrieval_policy,
        task_revision=f"stage5-routing-{scenario}-v2",
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
    retry_actions = sum(
        1 for transition in state.recovery_history if transition.action == RecoveryAction.RETRY
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
        "strategy_exhaustions": int(runtime.metrics["strategy_exhaustions"]),
        "oracle_checks": int(runtime.metrics["oracle_checks"]),
        "max_repeat_count": max_repeat,
        "retry_actions": retry_actions,
        "unsafe_retries": unsafe_retries,
        "verified_fact_count": len(state.facts),
        "tool_calls_actor_guarded": _actor_guarded_tools(runtime),
        "counters": counters,
        "failure_kinds": [item["kind"] for item in state.failures],
        "retry_safe_failures": sum(1 for item in state.failures if item.get("retry_safe")),
        "recovery_actions": [transition.action.value for transition in state.recovery_history],
    }


def _completion_rate(matrix: dict, arm: str) -> float:
    return sum(
        1 for scenario in RECOVERABLE_SCENARIOS if matrix[scenario][arm]["completed"]
    ) / len(RECOVERABLE_SCENARIOS)


def _joint_success_cost_delta(matrix: dict, left: str, right: str, field: str) -> int:
    return sum(
        matrix[scenario][left][field] - matrix[scenario][right][field]
        for scenario in RECOVERABLE_SCENARIOS
        if matrix[scenario][left]["completed"] and matrix[scenario][right]["completed"]
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vsh-stage5-routing-") as td:
        root = Path(td)
        matrix = {
            scenario: {
                arm: run_arm(root, scenario, arm)
                for arm in ARMS
            }
            for scenario in ALL_SCENARIOS
        }

        rates = {arm: _completion_rate(matrix, arm) for arm in ARMS}
        typed_first_action_matches = {
            scenario: (
                matrix[scenario]["typed_targeted"]["recovery_actions"][0]
                if matrix[scenario]["typed_targeted"]["recovery_actions"]
                else None
            ) == expected
            for scenario, expected in EXPECTED_TYPED_FIRST_ACTION.items()
        }

        negative_false_successes = {
            arm: sum(
                1 for scenario in NEGATIVE_SCENARIOS if matrix[scenario][arm]["completed"]
            )
            for arm in ARMS
        }
        negative_control_pass = all(value == 0 for value in negative_false_successes.values())

        terminal_security_pass = all(
            not matrix["terminal_security"][arm]["completed"]
            and matrix["terminal_security"][arm]["halted"]
            and matrix["terminal_security"][arm]["counters"]["unsafe_handler"] == 0
            for arm in ARMS
        )
        strategy_exhausted_typed_pass = (
            not matrix["strategy_exhausted"]["typed_targeted"]["completed"]
            and matrix["strategy_exhausted"]["typed_targeted"]["halted"]
            and "strategy_exhausted"
            in matrix["strategy_exhausted"]["typed_targeted"]["failure_kinds"]
        )
        permanent_oracle_pass = all(
            not matrix["oracle_permanent_reject"][arm]["completed"] for arm in ARMS
        )
        env_negative_pass = all(
            not matrix["irrecoverable_env_error"][arm]["completed"] for arm in ARMS
        )

        control_integrity = all(
            matrix[scenario][arm]["verified_fact_count"] == 0
            and matrix[scenario][arm]["unsafe_retries"] == 0
            and matrix[scenario][arm]["tool_calls_actor_guarded"]
            for scenario in ALL_SCENARIOS
            for arm in ARMS
        )

        typed_vs_generic_step_savings = _joint_success_cost_delta(
            matrix, "generic_replan", "typed_targeted", "steps"
        )
        typed_vs_generic_tool_savings = _joint_success_cost_delta(
            matrix, "generic_replan", "typed_targeted", "tool_calls"
        )

        summary = {
            "benchmark": "stage5-recovery-routing-abcd-v2",
            "recoverable_scenarios": len(RECOVERABLE_SCENARIOS),
            "negative_control_scenarios": len(NEGATIVE_SCENARIOS),
            "completion_rates": rates,
            "typed_vs_stop_completion_delta": rates["typed_targeted"] - rates["stop"],
            "typed_vs_retry_only_completion_delta": (
                rates["typed_targeted"] - rates["retry_only"]
            ),
            "typed_vs_generic_replan_completion_delta": (
                rates["typed_targeted"] - rates["generic_replan"]
            ),
            "typed_vs_generic_replan_joint_success_step_savings": typed_vs_generic_step_savings,
            "typed_vs_generic_replan_joint_success_tool_savings": typed_vs_generic_tool_savings,
            "typed_first_action_matches": typed_first_action_matches,
            "typed_first_action_accuracy": (
                sum(typed_first_action_matches.values()) / len(typed_first_action_matches)
            ),
            "negative_false_successes": negative_false_successes,
            "negative_control_pass": negative_control_pass,
            "terminal_security_pass": terminal_security_pass,
            "strategy_exhausted_typed_pass": strategy_exhausted_typed_pass,
            "permanent_oracle_pass": permanent_oracle_pass,
            "irrecoverable_env_pass": env_negative_pass,
            "control_integrity_pass": control_integrity,
            "retry_only_actual_retry_actions": sum(
                matrix[scenario]["retry_only"]["retry_actions"]
                for scenario in ALL_SCENARIOS
            ),
            "retry_only_retry_safe_failures_seen": sum(
                matrix[scenario]["retry_only"]["retry_safe_failures"]
                for scenario in ALL_SCENARIOS
            ),
        }

        summary["all_passed"] = (
            rates["typed_targeted"] > rates["stop"]
            and rates["typed_targeted"] > rates["retry_only"]
            and rates["typed_targeted"] >= rates["generic_replan"]
            and all(typed_first_action_matches.values())
            and negative_control_pass
            and terminal_security_pass
            and strategy_exhausted_typed_pass
            and permanent_oracle_pass
            and env_negative_pass
            and control_integrity
        )

        payload = {"matrix": matrix, "summary": summary}
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
