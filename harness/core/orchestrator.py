from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Mapping, Sequence

from harness.core.contracts import (
    Action,
    LoopStage,
    LoopState,
    Observation,
    VerificationResult,
    normalize_criteria,
)
from harness.core.verification import verify_criteria
from harness.core.workflow import run_intake_workflow

Reasoner = Callable[[LoopState, dict], Action | None]
Executor = Callable[[Action], Observation]
Verifier = Callable[[LoopState], VerificationResult]


def default_verifier(state: LoopState) -> VerificationResult:
    return verify_criteria(state.success_criteria, state.evidence)


class ClosedLoopOrchestrator:
    """Deterministic orchestration shell around the existing intake workflow.

    The orchestrator intentionally does not own an LLM provider or a command runner.
    Reasoning, execution, and semantic verification are injectable so the meta layer
    stays testable and does not silently turn bounded discovery into arbitrary action.
    """

    def __init__(
        self,
        *,
        reasoner: Reasoner,
        executor: Executor,
        verifier: Verifier | None = None,
        max_iterations: int = 8,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        self.reasoner = reasoner
        self.executor = executor
        self.verifier = verifier or default_verifier
        self.max_iterations = max_iterations

    def run(
        self,
        user_request: str,
        *,
        workspace_path: str | Path = ".",
        provided_files: Sequence[str | Path] | None = None,
        success_criteria: Sequence[str | Mapping[str, object]] | None = None,
    ) -> dict:
        intake_result = run_intake_workflow(
            user_request,
            workspace_path=workspace_path,
            provided_files=provided_files,
        )
        criteria = normalize_criteria(success_criteria)
        state = LoopState(
            objective=str(intake_result["intake"]["objective"]),
            stage=LoopStage.REASON,
            success_criteria=criteria,
        )

        verification = self.verifier(state)

        for _ in range(self.max_iterations):
            action = self.reasoner(state, intake_result)
            if action is None:
                verification = self.verifier(state)
                final_stage = LoopStage.COMPLETE if verification.passed else LoopStage.BLOCKED
                state = replace(state, stage=final_stage)
                break

            state = replace(state, stage=LoopStage.ACT, last_action=action)
            observation = self.executor(action)
            state = state.with_observation(observation)
            state = replace(state, stage=LoopStage.VERIFY)
            verification = self.verifier(state)

            if verification.passed:
                state = replace(state, stage=LoopStage.COMPLETE)
                break

            state = replace(state, stage=LoopStage.REASON)
        else:
            verification = self.verifier(state)
            state = replace(
                state,
                stage=LoopStage.BLOCKED,
                notes=state.notes + ("iteration budget exhausted",),
            )

        return {
            "intake": intake_result,
            "state": state,
            "verification": verification,
        }
