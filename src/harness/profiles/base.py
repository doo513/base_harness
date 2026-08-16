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
    def completion_oracle(self): return NeverAcceptOracle()
