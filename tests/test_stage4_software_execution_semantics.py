from __future__ import annotations

from pathlib import Path

import pytest

from harness.core.budget import Budget
from harness.core.controller import ScriptedController
from harness.core.runtime import HarnessRuntime
from harness.core.state import Authority, Claim
from harness.core.storage import ArtifactStore
from harness.profiles.software import SoftwareProfile


def runtime(tmp_path: Path, name: str) -> HarnessRuntime:
    workspace = tmp_path / f"{name}-workspace"
    workspace.mkdir()
    profile = SoftwareProfile(
        workspace=workspace,
        acceptance_commands=["python -c \"raise SystemExit(0)\""],
    )
    return HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=tmp_path / f"{name}-run",
        workspace=workspace,
        budget=Budget(hard_max_steps=10),
        task_revision=f"{name}-v1",
    )


def tool_artifact(rt: HarnessRuntime, *, ok=True, returncode=0, stdout="", stderr="", timed_out=False):
    ref = rt.artifacts.put_json(
        "tool.json",
        {
            "ok": ok,
            "output": {
                "returncode": returncode,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": timed_out,
            },
            "error": None if ok else "postcondition failed",
        },
    )
    rt.state.artifacts.append(ref)
    rt.state.evidence_refs.append(ref)
    return ref


def verify(rt: HarnessRuntime, key: str, value, ref: str) -> bool:
    rt.state.propose(Claim(key, value, evidence_refs=[ref]))
    rt._verify_claim(key)
    return key in rt.state.facts


def test_build_success_claim_commits_environment_authority(tmp_path):
    rt = runtime(tmp_path, "build-pass")
    ref = tool_artifact(rt, ok=True, returncode=0)
    assert verify(rt, "software.build_result.main", {"succeeded": True}, ref)
    assert rt.state.facts["software.build_result.main"].authority == Authority.ENVIRONMENT


def test_build_success_claim_rejects_nonzero_execution(tmp_path):
    rt = runtime(tmp_path, "build-fail-positive")
    ref = tool_artifact(rt, ok=False, returncode=1, stderr="syntax error")
    assert not verify(rt, "software.build_result.main", {"succeeded": True}, ref)


def test_build_failure_claim_accepts_observed_failed_execution(tmp_path):
    rt = runtime(tmp_path, "build-failure-claim")
    ref = tool_artifact(rt, ok=False, returncode=1, stderr="syntax error")
    assert verify(rt, "software.build_result.main", {"succeeded": False}, ref)


def test_test_result_claims_are_bound_to_test_verifier(tmp_path):
    rt = runtime(tmp_path, "test-pass")
    ref = tool_artifact(rt, ok=True, returncode=0, stdout="1 passed\n")
    assert verify(rt, "software.test_result.unit", {"succeeded": True}, ref)
    assert rt.state.facts["software.test_result.unit"].authority == Authority.ENVIRONMENT


def test_timeout_cannot_satisfy_success_claim(tmp_path):
    rt = runtime(tmp_path, "timeout")
    ref = tool_artifact(rt, ok=False, returncode=-1, timed_out=True)
    assert not verify(rt, "software.test_result.timeout", {"succeeded": True}, ref)


def test_behavior_requires_exact_successful_stdout(tmp_path):
    exact = runtime(tmp_path, "behavior-exact")
    exact_ref = tool_artifact(exact, stdout="READY\n")
    assert verify(exact, "software.behavioral_acceptance.cli", {"stdout_equals": "READY\n"}, exact_ref)

    near = runtime(tmp_path, "behavior-near")
    near_ref = tool_artifact(near, stdout="READY!\n")
    assert not verify(near, "software.behavioral_acceptance.cli", {"stdout_equals": "READY\n"}, near_ref)


def test_freeform_and_generic_assertion_cannot_masquerade_as_build_result(tmp_path):
    freeform = runtime(tmp_path, "freeform")
    ref = tool_artifact(freeform)
    assert not verify(freeform, "software.build_result.main", "build passed", ref)

    generic = runtime(tmp_path, "generic-mask")
    generic_ref = tool_artifact(generic)
    candidate = {"kind": "artifact_json_assertion", "path": ["ok"], "operator": "eq", "expected": True}
    assert not verify(generic, "software.build_result.main", candidate, generic_ref)


def test_unregistered_or_tampered_evidence_fails_closed(tmp_path):
    missing = runtime(tmp_path, "missing-ref")
    external_ref = missing.artifacts.put_json(
        "external.json",
        {"ok": True, "output": {"returncode": 0, "stdout": "", "stderr": "", "timed_out": False}, "error": None},
    )
    # Artifact exists physically but is not registered in HarnessState.
    assert not verify(missing, "software.build_result.main", {"succeeded": True}, external_ref)

    tampered = runtime(tmp_path, "tampered")
    ref = tool_artifact(tampered)
    path = ArtifactStore.resolve_ref_path(tampered.artifacts.root, ref)
    path.write_text("tampered", encoding="utf-8")
    assert not verify(tampered, "software.build_result.main", {"succeeded": True}, ref)


def test_unknown_software_semantic_prefix_is_rejected_by_registry(tmp_path):
    rt = runtime(tmp_path, "unknown-prefix")
    ref = tool_artifact(rt)
    assert not verify(rt, "software.security_property.safe", {"succeeded": True}, ref)
    assert "software.security_property.safe" not in rt.state.facts
