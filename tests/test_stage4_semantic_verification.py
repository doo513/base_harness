from __future__ import annotations

import json

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision, ScriptedController
from harness.core.runtime import HarnessRuntime
from harness.core.state import Authority
from harness.core.storage import ArtifactStore
from harness.core.verification import (
    EvidenceRefVerifier,
    ExistsVerifier,
    StructuredArtifactAssertionVerifier,
    VerificationContract,
    VerificationLevel,
    VerificationRequirement,
    VerificationResult,
    VerifierChain,
)
from harness.profiles.base import DomainProfile
from harness.profiles.software import SoftwareProfile


def semantic_contract():
    return VerificationContract(
        minimum_level=VerificationLevel.EXECUTION,
        requirements=(
            VerificationRequirement("candidate_exists", VerificationLevel.SCHEMA),
            VerificationRequirement("evidence_present", VerificationLevel.STRUCTURAL, require_evidence=True),
            VerificationRequirement("artifact_semantics", VerificationLevel.EXECUTION, require_evidence=True, minimum_confidence=1.0),
        ),
    )


def make_artifact(tmp_path, payload):
    store = ArtifactStore(tmp_path / "artifacts")
    ref = store.put_json("evidence.json", payload)
    return store, ref


def context(store, ref):
    return {
        "state": {"artifacts": [ref]},
        "claim_evidence_refs": [ref],
        "artifact_root": str(store.root),
        "claim_key": "claim",
    }


def assertion(expected, path=None):
    return {
        "kind": "artifact_json_assertion",
        "path": path or ["output", "returncode"],
        "operator": "eq",
        "expected": expected,
    }


def test_verifier_result_cannot_inflate_declared_level():
    class InflatingVerifier:
        name = "inflating"
        level = VerificationLevel.STRUCTURAL
        covers = ("artifact_semantics",)
        def verify(self, candidate, context):
            return VerificationResult(True, VerificationLevel.EXTERNAL_ORACLE, "fake elevation", coverage=["artifact_semantics"])

    result = VerifierChain([InflatingVerifier()]).run("x", {})[0]
    assert result.verified is False
    assert result.level == VerificationLevel.STRUCTURAL
    assert "different from its declaration" in result.reason


def test_result_supplied_coverage_is_not_trusted():
    class CoverageSpoofer:
        name = "spoofer"
        level = VerificationLevel.EXECUTION
        covers = ()
        def verify(self, candidate, context):
            return VerificationResult(True, self.level, "pretend semantic", coverage=["artifact_semantics"], evidence_refs=["artifact://fake"], confidence=1.0)

    results = VerifierChain([CoverageSpoofer()]).run("x", {})
    assessment = VerificationContract(
        VerificationLevel.EXECUTION,
        (VerificationRequirement("artifact_semantics", VerificationLevel.EXECUTION, require_evidence=True),),
    ).assess(results)
    assert results[0].coverage == []
    assert assessment.accepted is False


def test_contract_rejects_evidence_free_semantic_success():
    result = VerificationResult(
        True,
        VerificationLevel.EXECUTION,
        "bool only",
        coverage=["artifact_semantics"],
        confidence=1.0,
    )
    contract = VerificationContract(
        VerificationLevel.EXECUTION,
        (VerificationRequirement("artifact_semantics", VerificationLevel.EXECUTION, require_evidence=True),),
    )
    assert contract.assess([result]).accepted is False


def test_structured_artifact_assertion_true_positive(tmp_path):
    store, ref = make_artifact(tmp_path, {"ok": True, "output": {"returncode": 0, "stdout": "ok"}})
    chain = VerifierChain([ExistsVerifier(), EvidenceRefVerifier(), StructuredArtifactAssertionVerifier()])
    results = chain.run(assertion(0), context(store, ref))
    assessment = semantic_contract().assess(results)
    assert assessment.accepted is True
    assert assessment.missing_requirements == []


def test_structured_artifact_assertion_true_negative(tmp_path):
    store, ref = make_artifact(tmp_path, {"ok": True, "output": {"returncode": 1}})
    chain = VerifierChain([ExistsVerifier(), EvidenceRefVerifier(), StructuredArtifactAssertionVerifier()])
    results = chain.run(assertion(0), context(store, ref))
    assert results[-1].verified is False
    assert semantic_contract().assess(results).accepted is False


def test_freeform_claim_cannot_satisfy_software_execution_contract(tmp_path):
    store, ref = make_artifact(tmp_path, {"ok": True, "output": {"returncode": 0}})
    chain = VerifierChain([ExistsVerifier(), EvidenceRefVerifier(), StructuredArtifactAssertionVerifier()])
    results = chain.run("tests passed", context(store, ref))
    assert semantic_contract().assess(results).accepted is False


def test_missing_or_wrong_artifact_path_fails_closed(tmp_path):
    store, ref = make_artifact(tmp_path, {"ok": True, "output": {"returncode": 0}})
    verifier = StructuredArtifactAssertionVerifier()
    result = verifier.verify(assertion(0, ["output", "does_not_exist"]), context(store, ref))
    assert result.verified is False
    assert "could not be evaluated" in result.reason


def test_adversarial_matrix_has_zero_fp_and_zero_fn(tmp_path):
    store, ref = make_artifact(tmp_path, {"ok": True, "output": {"returncode": 0, "stdout": "PASS"}, "meta": [3, 5]})
    chain = VerifierChain([ExistsVerifier(), EvidenceRefVerifier(), StructuredArtifactAssertionVerifier()])
    ctx = context(store, ref)
    cases = [
        (assertion(0), True),
        (assertion(1), False),
        (assertion("PASS", ["output", "stdout"]), True),
        (assertion("FAIL", ["output", "stdout"]), False),
        (assertion(5, ["meta", 1]), True),
        (assertion(3, ["meta", 1]), False),
        ({"kind": "artifact_json_assertion", "path": ["ok"], "operator": "eq", "expected": True}, True),
        ({"kind": "artifact_json_assertion", "path": ["ok"], "operator": "eq", "expected": False}, False),
    ]
    fp = fn = 0
    for candidate, gold in cases:
        predicted = semantic_contract().assess(chain.run(candidate, ctx)).accepted
        fp += int(predicted and not gold)
        fn += int((not predicted) and gold)
    assert fp == 0
    assert fn == 0


def test_software_profile_contract_is_execution_semantic():
    profile = SoftwareProfile(acceptance_commands=["false"])
    contract = profile.verification_contract()
    assert contract.minimum_level == VerificationLevel.EXECUTION
    assert {r.id for r in contract.requirements} == {"candidate_exists", "evidence_present", "artifact_semantics"}
    assert any(isinstance(v, StructuredArtifactAssertionVerifier) for v in profile.verifiers())


class StructuralProfile(DomainProfile):
    name = "structural-test"
    def default_goal(self):
        return GoalContract(goal="test", acceptance=["none"])
    def verifiers(self):
        return [ExistsVerifier(), EvidenceRefVerifier()]
    def minimum_verification_level(self):
        return VerificationLevel.STRUCTURAL
    def verification_contract(self):
        return VerificationContract(
            VerificationLevel.STRUCTURAL,
            (
                VerificationRequirement("candidate_exists", VerificationLevel.SCHEMA),
                VerificationRequirement("evidence_present", VerificationLevel.STRUCTURAL, require_evidence=True),
            ),
        )


def test_structural_claim_commits_as_supported_not_trusted_tool(tmp_path):
    runtime = HarnessRuntime(
        goal=StructuralProfile().default_goal(),
        profile=StructuralProfile(),
        controller=ScriptedController([]),
        run_dir=tmp_path / "run",
        workspace=tmp_path,
        budget=Budget(hard_max_steps=2),
    )
    ref = runtime.artifacts.put_json("evidence.json", {"observed": True})
    runtime.state.artifacts.append(ref)
    runtime.state.evidence_refs.append(ref)
    runtime.controller.decisions = [
        Decision("propose", {"key": "supported", "value": "observed", "evidence_refs": [ref]}),
        Decision("verify_claim", {"key": "supported"}),
    ]
    state = runtime.run()
    assert state.facts["supported"].authority == Authority.SUPPORTED


def test_runtime_commits_structured_execution_claim(tmp_path):
    profile = SoftwareProfile(workspace=tmp_path, acceptance_commands=["false"])
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=tmp_path / "run",
        workspace=tmp_path,
        budget=Budget(hard_max_steps=2),
    )
    ref = runtime.artifacts.put_json("execution.json", {"ok": True, "output": {"returncode": 0}})
    runtime.state.artifacts.append(ref)
    runtime.state.evidence_refs.append(ref)
    runtime.controller.decisions = [
        Decision("propose", {"key": "build.returncode", "value": assertion(0), "evidence_refs": [ref]}),
        Decision("verify_claim", {"key": "build.returncode"}),
    ]
    state = runtime.run()
    assert state.facts["build.returncode"].authority == Authority.ENVIRONMENT


def test_manifest_fingerprints_verification_contract(tmp_path):
    profile = SoftwareProfile(workspace=tmp_path, acceptance_commands=["false"])
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=tmp_path / "run",
        workspace=tmp_path,
        budget=Budget(hard_max_steps=0),
    )
    manifest = json.loads((tmp_path / "run" / "run_manifest.json").read_text(encoding="utf-8"))
    body = manifest["body"]
    contract = body["config"]["profile"]["verification_contract"]
    assert contract["minimum_level_name"] == "EXECUTION"
    assert any(r["id"] == "artifact_semantics" for r in contract["requirements"])
