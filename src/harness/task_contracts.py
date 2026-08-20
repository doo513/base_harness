from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from harness.core.contracts import GoalContract
from harness.core.oracles import CompletionResult
from harness.profiles.base import DomainProfile
from harness.profiles.domain_contracts import DomainPhase, DomainWorkflowContract


class EvidenceBackedArtifactOracle:
    """Accept a requested workspace artifact only after real project evidence exists.

    This is intentionally a task-level integration oracle rather than a new
    domain mode. It preserves the selected profile's tools/security boundary and
    changes only the completion contract for an explicit deliverable task.
    """

    name = "evidence_backed_artifact_oracle"

    def __init__(self, target: str, *, min_bytes: int = 256, min_workspace_evidence: int = 2):
        path = Path(target)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("artifact target must be a relative path inside the workspace")
        self.target = path.as_posix()
        self.min_bytes = int(min_bytes)
        self.min_workspace_evidence = int(min_workspace_evidence)

    def evaluate(self, *, goal, state, workspace):
        root = Path(workspace).expanduser().resolve()
        target = (root / self.target).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return CompletionResult(
                False,
                "artifact target escapes workspace",
                oracle_id=self.name,
                independence_level="harness_fixed",
            )

        observations = [
            item
            for item in state.observations
            if bool(getattr(item, "ok", False))
            and getattr(item, "source", "") in {"file.read", "directory.list", "file.search"}
            and isinstance(getattr(item, "artifact_ref", None), str)
            and getattr(item, "artifact_ref") in state.evidence_refs
        ]
        file_reads = [item for item in observations if getattr(item, "source", "") == "file.read"]

        if len(observations) < self.min_workspace_evidence or not file_reads:
            return CompletionResult(
                False,
                "insufficient workspace evidence collected before artifact synthesis",
                evidence=[{
                    "workspace_evidence": len(observations),
                    "file_reads": len(file_reads),
                    "required_workspace_evidence": self.min_workspace_evidence,
                }],
                oracle_id=self.name,
                independence_level="harness_fixed",
                coverage={"workspace_evidence": len(observations), "file_reads": len(file_reads)},
            )

        if not target.exists() or not target.is_file():
            return CompletionResult(
                False,
                f"requested artifact does not exist: {self.target}",
                evidence=[{"evidence_refs": [item.artifact_ref for item in observations]}],
                oracle_id=self.name,
                independence_level="harness_fixed",
            )

        try:
            raw = target.read_bytes()
        except OSError as exc:
            return CompletionResult(
                False,
                f"requested artifact cannot be read: {exc}",
                oracle_id=self.name,
                independence_level="harness_fixed",
            )
        if len(raw) < self.min_bytes:
            return CompletionResult(
                False,
                f"requested artifact is too small to satisfy the deliverable contract: {len(raw)} bytes",
                oracle_id=self.name,
                independence_level="harness_fixed",
                coverage={"artifact_bytes": len(raw)},
            )

        evidence_refs = list(dict.fromkeys(item.artifact_ref for item in observations))
        evidence: list[dict[str, Any]] = [{
            "artifact_target": self.target,
            "artifact_sha256": hashlib.sha256(raw).hexdigest(),
            "artifact_bytes": len(raw),
            "workspace_evidence_refs": evidence_refs,
            "workspace_evidence": len(evidence_refs),
            "file_reads": len(file_reads),
        }]
        canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
        return CompletionResult(
            True,
            "requested artifact exists and was produced after workspace evidence collection",
            evidence=evidence,
            oracle_id=self.name,
            independence_level="harness_fixed",
            evidence_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            coverage={
                "artifact_bytes": len(raw),
                "workspace_evidence": len(evidence_refs),
                "file_reads": len(file_reads),
            },
        )


class EvidenceArtifactTaskProfile(DomainProfile):
    """Task-contract overlay for evidence-backed reports/documents.

    The selected domain profile still owns tools, verifiers, permissions and
    evaluation semantics. This overlay only supplies task-specific workflow and
    completion semantics, avoiding a separate user-visible Research mode.
    """

    def __init__(self, base: DomainProfile, *, artifact_target: str):
        self.base = base
        self.artifact_target = artifact_target
        self.name = base.name
        self.workspace = getattr(base, "workspace", ".")

    def default_goal(self):
        base_goal = self.base.default_goal()
        return GoalContract(
            goal=base_goal.goal,
            acceptance=[
                f"produce requested evidence-backed artifact: {self.artifact_target}",
                "collect relevant workspace evidence before synthesis",
                "recheck the deliverable against the original request before completion",
            ],
            constraints=[
                *base_goal.constraints,
                "start with an explicit plan/checklist and keep later work aligned to it",
                "base findings on inspected workspace evidence; do not invent unsupported project facts",
                "inspect relevant source files before writing the final artifact",
            ],
            pinned_constraints=[
                *base_goal.pinned_constraints,
                f"final artifact path is {self.artifact_target}",
                "completion requires harness-observed workspace evidence and the requested artifact",
            ],
        )

    def tools(self):
        return self.base.tools()

    def verifiers(self):
        return self.base.verifiers()

    def minimum_verification_level(self):
        return self.base.minimum_verification_level()

    def verification_contract(self):
        return self.base.verification_contract()

    def claim_verification_registry(self):
        return self.base.claim_verification_registry()

    def workflow_contract(self):
        return DomainWorkflowContract(
            name="evidence-backed-artifact",
            phases=(
                DomainPhase("plan", "Translate the user request into a concrete checklist of questions, scope, and deliverable requirements."),
                DomainPhase("inspect", "Map the target workspace and inspect project metadata, documentation, entry points, source, tests, and configuration relevant to the checklist."),
                DomainPhase("evidence", "Collect enough direct workspace evidence to support the important findings; prefer file.read/directory.list/file.search over unsupported assumptions."),
                DomainPhase("analyze", "Reconcile the collected evidence against the checklist and identify gaps before synthesis."),
                DomainPhase("synthesize", f"Create {self.artifact_target} inside the workspace, grounding findings in the inspected project sources."),
                DomainPhase("recheck", "Re-read the deliverable and compare it with the original request/checklist; correct omissions or unsupported conclusions."),
                DomainPhase("acceptance", "Request completion only after the requested artifact exists and the evidence-backed completion contract is ready to pass."),
            ),
            guidance=(
                "the checklist is actor workflow bookkeeping, not trusted truth",
                "workspace observations are evidence, and any promoted factual claim still follows the normal verifier path",
                "do not substitute test execution for evidence collection when the requested deliverable is analysis/documentation",
            ),
        )

    def evaluation_contract(self):
        return self.base.evaluation_contract()

    def task_progress_snapshot(self, *, goal, state):
        evidence = [
            item
            for item in state.observations
            if bool(getattr(item, "ok", False))
            and getattr(item, "source", "") in {"file.read", "directory.list", "file.search"}
        ]
        milestones: list[str] = []
        if evidence:
            milestones.append("workspace_evidence_started")
        if len(evidence) >= 2:
            milestones.append("workspace_evidence_sufficient_for_artifact_gate")
        if any(getattr(item, "source", "") == "file.read" for item in evidence):
            milestones.append("source_file_inspected")
        return {"milestones": milestones, "score": float(len(milestones))}

    def completion_oracle(self):
        return EvidenceBackedArtifactOracle(self.artifact_target)
