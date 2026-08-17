from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Sequence

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


class ClosedLoopOrchestrator:
    """Deterministic orchestration shell around the existing intake workflow.

    The orchestrator intentionally does not own an LLM provider or a command runner.
    Those capabilities are injected as `reasoner` and `executor`, which keeps the
    meta layer testable and prevents this scaffold from silently executing arbitrary
    actions.
    """

    def __init__(
        self,
        *,
        reasoner: Reasoner,
        executor: Executor,
        max_iterations: int = 8,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        self.reasoner = reasoner
        self.executor = executor
        self.max_iterations = max_iterations

    def run(
        self,
        user_request: str,
        *,
        workspace_path: str | Path = ".",
        provided_files: Sequence[str | Path] | None = None,
        success_criteria: Sequence[str | dict] | None = None,
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

        verification: VerificationResult = verify_criteria(state.success_criteria, state.evidence)

        for _ in range(self.max_iterations):
            action = self.reasoner(state, intake_result)
            if action is None:
                verification = verify_criteria(state.success_criteria, state.evidence)
                final_stage = LoopStage.COMPLETE if verification.passed else LoopStage.BLOCKED
                state = replace(state, stage=final_stage)
                break

            state = replace(state, stage=LoopStage.ACT, last_action=action)
            observation = self.executor(action)
            state = state.with_observation(observation)
            verification = verify_criteria(state.success_criteria, state.evidence)
            state = replace(state, stage=LoopStage.VERIFY)

            if verification.passed:
                state = replace(state, stage=LoopStage.COMPLETE)
                break

            state = replace(state, stage=LoopStage.REASON)
        else:
            verification = verify_criteria(state.success_criteria, state.evidence)
            state = replace(state, stage=LoopStage.BLOCKED, notes=state.notes + ("iteration budget exhausted",))

        return {
            "intake": intake_result,
            "state": state,
            "verification": verification,
        }
