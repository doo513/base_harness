from harness.core.contracts import GoalContract
from harness.core.verification import ExistsVerifier, EvidenceRefVerifier, VerificationLevel
from harness.core.oracles import CommandCompletionOracle, SealedCommandCompletionOracle, NeverAcceptOracle
from harness.core.tools import make_shell_tool
from .base import DomainProfile

class HackathonProfile(DomainProfile):
    name = "hackathon"

    def __init__(
        self,
        *,
        workspace=".",
        acceptance_commands=None,
        execution_backend=None,
        oracle_backend=None,
        sealed_oracle_root=None,
        require_oracle_isolation=False,
    ):
        self.workspace = workspace
        self.acceptance_commands = list(acceptance_commands or [])
        self.execution_backend = execution_backend
        self.oracle_backend = oracle_backend
        self.sealed_oracle_root = sealed_oracle_root
        self.require_oracle_isolation = require_oracle_isolation

    def default_goal(self):
        return GoalContract(
            goal="Deliver a demonstrable product within the deadline.",
            acceptance=["build succeeds", "demo path works", "judging criteria visibly covered"],
            constraints=[
                "separate hard verification from soft quality evaluation",
                "cut/mock low-value blockers after repeated failure",
            ],
            pinned_constraints=["protect rehearsal/deadline buffer"],
        )

    def tools(self):
        return {"shell": make_shell_tool(self.workspace, backend=self.execution_backend)}

    def verifiers(self):
        return [ExistsVerifier(), EvidenceRefVerifier()]

    def minimum_verification_level(self):
        return VerificationLevel.STRUCTURAL

    def completion_oracle(self):
        if not self.acceptance_commands:
            return NeverAcceptOracle("hackathon profile requires fixed build/demo acceptance command(s)")
        if self.sealed_oracle_root:
            return SealedCommandCompletionOracle(
                self.acceptance_commands,
                sealed_root=self.sealed_oracle_root,
                backend=(self.oracle_backend or self.execution_backend),
                require_filesystem_isolation=self.require_oracle_isolation,
            )
        return CommandCompletionOracle(self.acceptance_commands)
