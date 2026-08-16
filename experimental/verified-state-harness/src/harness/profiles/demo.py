from harness.core.contracts import GoalContract
from harness.core.verification import ExistsVerifier, VerificationLevel
from harness.core.oracles import PredicateCompletionOracle, CompletionResult
from .base import DomainProfile

class DemoProfile(DomainProfile):
    name = "demo"

    def default_goal(self):
        return GoalContract(
            goal="Demonstrate that an actor cannot self-authorize completion.",
            acceptance=["verified demo.started fact exists"],
            constraints=["completion is decided by harness-side oracle"],
            pinned_constraints=["actor completion request is not sufficient"],
        )

    def verifiers(self):
        return [ExistsVerifier()]

    def minimum_verification_level(self):
        return VerificationLevel.SCHEMA

    def completion_oracle(self):
        def check(*, goal, state, workspace):
            claim = state.facts.get("demo.started")
            ok = bool(claim and claim.value is True)
            return CompletionResult(ok, "verified demo.started present" if ok else "missing verified demo.started")
        return PredicateCompletionOracle(check, name="demo_oracle")
