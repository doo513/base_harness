from harness.core.contracts import GoalContract
from harness.core.verification import (
    ExistsVerifier,
    EvidenceRefVerifier,
    StructuredArtifactAssertionVerifier,
    VerificationContract,
    VerificationRequirement,
    VerificationLevel,
)
from harness.core.claim_contracts import ClaimContractRegistry, ClaimContractRule
from harness.core.oracles import CommandCompletionOracle, SealedCommandCompletionOracle, NeverAcceptOracle
from harness.core.tools import make_shell_tool
from .base import DomainProfile


class SoftwareProfile(DomainProfile):
    name = "software"

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
            goal="Implement the requested change and satisfy acceptance criteria.",
            acceptance=["build/typecheck", "tests", "acceptance criteria"],
            constraints=["do not mutate tests solely to force a pass", "preserve regression evidence"],
            pinned_constraints=["verification evidence must be reproducible"],
        )

    def tools(self):
        return {"shell": make_shell_tool(self.workspace, backend=self.execution_backend)}

    def verifiers(self):
        return [ExistsVerifier(), EvidenceRefVerifier(), StructuredArtifactAssertionVerifier()]

    def minimum_verification_level(self):
        return VerificationLevel.EXECUTION

    def verification_contract(self):
        return VerificationContract(
            minimum_level=VerificationLevel.EXECUTION,
            requirements=(
                VerificationRequirement("candidate_exists", VerificationLevel.SCHEMA),
                VerificationRequirement("evidence_present", VerificationLevel.STRUCTURAL, require_evidence=True),
                VerificationRequirement("artifact_semantics", VerificationLevel.EXECUTION, require_evidence=True, minimum_confidence=1.0),
            ),
        )

    def claim_verification_registry(self):
        return ClaimContractRegistry((
            ClaimContractRule(
                claim_class="software.artifact_assertion",
                key_prefix="artifact_assertion.",
                contract=self.verification_contract(),
                allowed_verifiers=("exists", "evidence_ref", "structured_artifact_assertion"),
            ),
        ))

    def completion_oracle(self):
        if not self.acceptance_commands:
            return NeverAcceptOracle("software profile requires fixed --accept-command oracle(s)")
        if self.sealed_oracle_root:
            return SealedCommandCompletionOracle(
                self.acceptance_commands,
                sealed_root=self.sealed_oracle_root,
                backend=(self.oracle_backend or self.execution_backend),
                require_filesystem_isolation=self.require_oracle_isolation,
            )
        return CommandCompletionOracle(self.acceptance_commands)
