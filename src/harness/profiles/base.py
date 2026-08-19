from abc import ABC, abstractmethod
from harness.core.verification import VerificationContract, VerificationLevel
from harness.core.oracles import NeverAcceptOracle


class DomainProfile(ABC):
    name = "base"

    @abstractmethod
    def default_goal(self): ...

    def tools(self): return {}
    def verifiers(self): return []
    def minimum_verification_level(self): return VerificationLevel.LOGICAL
    def verification_contract(self):
        return VerificationContract.legacy(self.minimum_verification_level())
    def claim_verification_registry(self):
        """Optional strict claim-class registry.

        ``None`` preserves legacy profile behavior. Profiles that expose a
        registry fail closed when a claim key does not resolve to a declared
        claim class.
        """
        return None
    def workflow_contract(self):
        """Optional harness-supplied domain execution workflow guidance."""
        return None
    def evaluation_contract(self):
        """Optional advisory quality/rubric contract with no truth authority."""
        return None
    def task_progress_snapshot(self, *, goal, state):
        """Optional deterministic, monotonic task/world progress snapshot.

        Returning ``None`` grants no task/world progress authority. A profile
        that opts in must consistently return an object with only these fields:

        ``milestones``: unique stable strings representing achieved milestones.
        ``score``: a finite non-negative numeric progress score.

        The kernel grants task progress only when milestones are added without
        removal and/or score increases without decrease. Regression, Actor prose,
        retrieval content, or arbitrary snapshot churn has no reset authority.
        The hook must be pure with respect to durable HarnessState.
        """
        return None
    def completion_oracle(self): return NeverAcceptOracle()
