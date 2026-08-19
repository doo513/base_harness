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
from harness.core.tools import make_shell_tool, make_argv_tool
from .software_verification import (
    SoftwareBuildResultVerifier,
    SoftwareTestResultVerifier,
    SoftwareBehavioralAcceptanceVerifier,
)
from .domain_contracts import (
    DomainEvaluationContract,
    DomainPhase,
    DomainWorkflowContract,
    SoftCriterion,
)
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
        return {
            "shell": make_shell_tool(self.workspace, backend=self.execution_backend),
            "argv": make_argv_tool(self.workspace, backend=self.execution_backend),
        }

    def verifiers(self):
        return [
            ExistsVerifier(),
            EvidenceRefVerifier(),
            StructuredArtifactAssertionVerifier(),
            SoftwareBuildResultVerifier(),
            SoftwareTestResultVerifier(),
            SoftwareBehavioralAcceptanceVerifier(),
        ]

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

    @staticmethod
    def _software_execution_contract(coverage: str):
        return VerificationContract(
            minimum_level=VerificationLevel.EXECUTION,
            requirements=(
                VerificationRequirement("candidate_exists", VerificationLevel.SCHEMA),
                VerificationRequirement("evidence_present", VerificationLevel.STRUCTURAL, require_evidence=True),
                VerificationRequirement(coverage, VerificationLevel.EXECUTION, require_evidence=True, minimum_confidence=1.0),
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
            ClaimContractRule(
                claim_class="software.build_result",
                key_prefix="software.build_result.",
                contract=self._software_execution_contract("software_build_execution"),
                allowed_verifiers=("exists", "evidence_ref", "software_build_result"),
            ),
            ClaimContractRule(
                claim_class="software.test_result",
                key_prefix="software.test_result.",
                contract=self._software_execution_contract("software_test_execution"),
                allowed_verifiers=("exists", "evidence_ref", "software_test_result"),
            ),
            ClaimContractRule(
                claim_class="software.behavioral_acceptance",
                key_prefix="software.behavioral_acceptance.",
                contract=self._software_execution_contract("software_behavior_execution"),
                allowed_verifiers=("exists", "evidence_ref", "software_behavioral_acceptance"),
            ),
        ))

    def workflow_contract(self):
        return DomainWorkflowContract(
            name="software-development",
            phases=(
                DomainPhase("inspect", "Map the relevant repository structure, constraints, and existing tests."),
                DomainPhase("reproduce", "Reproduce or otherwise establish the requested behavior/problem before changing code."),
                DomainPhase("plan", "Choose the smallest change that addresses the goal without weakening tests or constraints."),
                DomainPhase("implement", "Apply the code/configuration change inside the workspace."),
                DomainPhase(
                    "targeted_verify",
                    "Run the narrowest relevant build/test/behavior checks and promote only verifier-backed results.",
                    ("software.build_result.*", "software.test_result.*", "software.behavioral_acceptance.*"),
                ),
                DomainPhase(
                    "regression",
                    "Run broader regression/build checks after the targeted change is stable.",
                    ("software.build_result.*", "software.test_result.*"),
                ),
                DomainPhase("acceptance", "Request completion only after fixed harness-side acceptance criteria are ready to pass."),
            ),
            guidance=(
                "prefer structured read/argv tools over shell when they can express the action",
                "do not treat a task checkbox or successful command alone as stronger semantic proof than its verifier contract",
                "retain failing evidence long enough to explain the corrective change",
            ),
        )

    def evaluation_contract(self):
        return DomainEvaluationContract(
            criteria=(
                SoftCriterion("scope_minimality", "Change only what is needed for the requested behavior."),
                SoftCriterion("maintainability", "Keep the implementation understandable and consistent with the repository."),
                SoftCriterion("regression_risk", "Minimize unverified impact outside the target behavior."),
            ),
            guidance=("soft quality assessment is advisory and never substitutes for build/test/oracle evidence",),
        )

    def task_progress_snapshot(self, *, goal, state):
        milestones: list[str] = []
        facts = state.facts
        if any(key.startswith("artifact_assertion.") for key in facts):
            milestones.append("verified_artifact_assertion")
        if any(
            key.startswith("software.build_result.") and claim.value == {"succeeded": True}
            for key, claim in facts.items()
        ):
            milestones.append("build_passed")
        if any(
            key.startswith("software.test_result.") and claim.value == {"succeeded": True}
            for key, claim in facts.items()
        ):
            milestones.append("tests_passed")
        if any(key.startswith("software.behavioral_acceptance.") for key in facts):
            milestones.append("behavioral_acceptance_verified")
        return {"milestones": milestones, "score": float(len(milestones))}

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
