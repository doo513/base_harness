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
from .domain_contracts import (
    DomainEvaluationContract,
    DomainPhase,
    DomainWorkflowContract,
    SoftCriterion,
)
from .hackathon_verification import (
    HackathonBuildCheckVerifier,
    HackathonDemoCheckVerifier,
    HackathonRehearsalCheckVerifier,
)
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
        return {
            "shell": make_shell_tool(self.workspace, backend=self.execution_backend),
            "argv": make_argv_tool(self.workspace, backend=self.execution_backend),
        }

    def verifiers(self):
        return [
            ExistsVerifier(),
            EvidenceRefVerifier(),
            StructuredArtifactAssertionVerifier(),
            HackathonBuildCheckVerifier(),
            HackathonDemoCheckVerifier(),
            HackathonRehearsalCheckVerifier(),
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
    def _execution_contract(coverage: str):
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
                claim_class="hackathon.artifact_assertion",
                key_prefix="artifact_assertion.",
                contract=self.verification_contract(),
                allowed_verifiers=("exists", "evidence_ref", "structured_artifact_assertion"),
            ),
            ClaimContractRule(
                claim_class="hackathon.build_check",
                key_prefix="hackathon.build_check.",
                contract=self._execution_contract("hackathon_build_execution"),
                allowed_verifiers=("exists", "evidence_ref", "hackathon_build_check"),
            ),
            ClaimContractRule(
                claim_class="hackathon.demo_check",
                key_prefix="hackathon.demo_check.",
                contract=self._execution_contract("hackathon_demo_execution"),
                allowed_verifiers=("exists", "evidence_ref", "hackathon_demo_check"),
            ),
            ClaimContractRule(
                claim_class="hackathon.rehearsal_check",
                key_prefix="hackathon.rehearsal_check.",
                contract=self._execution_contract("hackathon_rehearsal_execution"),
                allowed_verifiers=("exists", "evidence_ref", "hackathon_rehearsal_check"),
            ),
        ))

    def workflow_contract(self):
        return DomainWorkflowContract(
            name="hackathon-delivery",
            phases=(
                DomainPhase("scope", "Lock the smallest demonstrable core value and map it to judging criteria."),
                DomainPhase("prototype", "Get one end-to-end happy path running before polishing secondary features."),
                DomainPhase(
                    "build_check",
                    "Verify that the deliverable builds/runs in the intended environment.",
                    ("hackathon.build_check.*",),
                ),
                DomainPhase(
                    "demo_check",
                    "Verify the exact demo path that will be shown to judges.",
                    ("hackathon.demo_check.*",),
                ),
                DomainPhase("polish", "Improve only high-value judging criteria without destabilizing the demo path."),
                DomainPhase(
                    "rehearsal",
                    "Rehearse the demo/presentation path and preserve deadline buffer.",
                    ("hackathon.rehearsal_check.*",),
                ),
                DomainPhase("acceptance", "Request completion only after fixed build/demo acceptance commands are ready to pass."),
            ),
            guidance=(
                "protect the verified demo path before adding optional features",
                "after repeated failure, prefer a bounded fallback/mock for low-value blockers when constraints allow it",
                "keep hard execution evidence separate from advisory judging-quality estimates",
            ),
        )

    def evaluation_contract(self):
        return DomainEvaluationContract(
            criteria=(
                SoftCriterion("problem_value", "How clearly the product addresses the target problem/user need."),
                SoftCriterion("demo_clarity", "How directly the demo communicates the core value."),
                SoftCriterion("judging_coverage", "How visibly the implementation supports stated judging criteria."),
                SoftCriterion("delivery_risk", "How likely remaining work is to destabilize the verified demo path."),
                SoftCriterion("presentation_readiness", "How ready the product/story is for a bounded rehearsal."),
            ),
            guidance=(
                "scores are advisory prioritization signals only",
                "soft evaluation cannot mark a build/demo/rehearsal check or final completion as passed",
            ),
        )

    def task_progress_snapshot(self, *, goal, state):
        milestones: list[str] = []
        facts = state.facts
        if any(key.startswith("artifact_assertion.") for key in facts):
            milestones.append("verified_artifact_assertion")
        for prefix, milestone in (
            ("hackathon.build_check.", "build_check_passed"),
            ("hackathon.demo_check.", "demo_check_passed"),
            ("hackathon.rehearsal_check.", "rehearsal_check_passed"),
        ):
            if any(
                key.startswith(prefix) and claim.value == {"succeeded": True}
                for key, claim in facts.items()
            ):
                milestones.append(milestone)
        return {"milestones": milestones, "score": float(len(milestones))}

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
        return CommandCompletionOracle(
            self.acceptance_commands,
            backend=(self.oracle_backend or self.execution_backend),
            require_filesystem_isolation=self.require_oracle_isolation,
        )
