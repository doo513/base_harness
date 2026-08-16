from harness.core.contracts import GoalContract
from harness.core.verification import ExistsVerifier, EvidenceRefVerifier, VerificationLevel
from harness.core.oracles import NeverAcceptOracle, PredicateCompletionOracle
from harness.core.tools import make_shell_tool
from .base import DomainProfile

class CTFProfile(DomainProfile):
    name = "ctf"

    def __init__(self, *, workspace=".", external_oracle=None, execution_backend=None):
        self.workspace = workspace
        self.external_oracle = external_oracle
        self.execution_backend = execution_backend

    def default_goal(self):
        return GoalContract(
            goal="Obtain a task-native externally accepted proof/flag.",
            acceptance=["local proof when possible", "remote verification", "external flag/proof acceptance"],
            constraints=[
                "unverified hypotheses never become facts",
                "preserve evidence",
                "do not retry refuted paths without new evidence",
            ],
            pinned_constraints=["final success requires task-native verification"],
        )

    def tools(self):
        return {"shell": make_shell_tool(self.workspace, backend=self.execution_backend)}

    def verifiers(self):
        return [ExistsVerifier(), EvidenceRefVerifier()]

    def minimum_verification_level(self):
        return VerificationLevel.STRUCTURAL

    def completion_oracle(self):
        if self.external_oracle is None:
            return NeverAcceptOracle("CTF success requires an operator-provided external flag/proof oracle")
        return PredicateCompletionOracle(self.external_oracle, name="ctf_external_oracle")
