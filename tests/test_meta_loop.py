from __future__ import annotations

import tempfile
import unittest

from harness.core.contracts import Action, Evidence, LoopStage, Observation, normalize_criteria
from harness.core.execution import observation_from_tool_result
from harness.core.orchestrator import ClosedLoopOrchestrator
from harness.core.verification import verify_criteria


class VerificationTests(unittest.TestCase):
    def test_verified_evidence_satisfies_required_criterion(self) -> None:
        criteria = normalize_criteria(["tests pass"])
        result = verify_criteria(criteria, [Evidence(type="test", criterion_id="C001", verified=True)])
        self.assertTrue(result.passed)
        self.assertEqual(result.satisfied_criteria, ("C001",))

    def test_unverified_evidence_does_not_satisfy_criterion(self) -> None:
        criteria = normalize_criteria(["tests pass"])
        result = verify_criteria(criteria, [Evidence(type="test", criterion_id="C001", verified=False)])
        self.assertFalse(result.passed)
        self.assertEqual(result.missing_criteria, ("C001",))

    def test_no_criteria_is_not_implicitly_verified(self) -> None:
        result = verify_criteria([], [])
        self.assertFalse(result.passed)
        self.assertIn("no success criteria defined", result.reasons)


class ExecutionTests(unittest.TestCase):
    def test_tool_result_becomes_typed_observation(self) -> None:
        action = Action(kind="command", name="unit-test")
        observation = observation_from_tool_result(
            action,
            {"returncode": 0, "stdout": "ok", "summary": "tests passed"},
            criterion_id="C001",
            expected="tests pass",
        )
        self.assertTrue(observation.ok)
        self.assertEqual(observation.exit_code, 0)
        self.assertTrue(observation.evidence[0].verified)
        self.assertEqual(observation.evidence[0].criterion_id, "C001")


class OrchestratorTests(unittest.TestCase):
    def test_closed_loop_completes_only_after_verified_evidence(self) -> None:
        calls = 0

        def reasoner(state, intake):
            nonlocal calls
            calls += 1
            return Action(kind="test", name="fixture-check")

        def executor(action):
            return Observation(
                action=action,
                ok=True,
                summary="fixture passed",
                evidence=(Evidence(type="test", criterion_id="C001", verified=True),),
            )

        with tempfile.TemporaryDirectory() as workspace:
            result = ClosedLoopOrchestrator(reasoner=reasoner, executor=executor, max_iterations=2).run(
                "Inspect this workspace and verify the fixture",
                workspace_path=workspace,
                success_criteria=["fixture is verified"],
            )

        self.assertEqual(calls, 1)
        self.assertEqual(result["state"].stage, LoopStage.COMPLETE)
        self.assertTrue(result["verification"].passed)
        self.assertEqual(result["state"].iteration, 1)


if __name__ == "__main__":
    unittest.main()
