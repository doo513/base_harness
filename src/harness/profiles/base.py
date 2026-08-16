from abc import ABC, abstractmethod
from harness.core.verification import VerificationLevel
from harness.core.oracles import NeverAcceptOracle

class DomainProfile(ABC):
    name = "base"

    @abstractmethod
    def default_goal(self): ...

    def tools(self): return {}
    def verifiers(self): return []
    def minimum_verification_level(self): return VerificationLevel.LOGICAL
    def completion_oracle(self): return NeverAcceptOracle()
