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
    def completion_oracle(self): return NeverAcceptOracle()
