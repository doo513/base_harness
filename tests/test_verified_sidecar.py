from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import pytest

from harness.verified_sidecar import PROTOCOL_VERSION, VerifiedSidecar, serve
from harness.verification_v2 import MAX_CAPTURE_CHARS, ProtocolError, redact


def message(
    request_type: str,
    payload: dict[str, object],
    *,
    run_id: str = "run-1",
    scope_id: str = "root",
    version: int = PROTOCOL_VERSION,
) -> dict[str, object]:
    return {
        "version": version,
        "id": request_type,
        "runId": run_id,
        "scopeId": scope_id,
        "type": request_type,
        "payload": payload,
    }


def source(text: str = "Verify the requested behavior") -> dict[str, str]:
    return {"sourceId": "user-1", "sourceType": "user_message", "text": text}


def source_ref(value: dict[str, str]) -> dict[str, str]:
    return {
        "sourceId": value["sourceId"],
        "sourceType": value["sourceType"],
        "sha256": hashlib.sha256(value["text"].encode()).hexdigest(),
    }


def attach_candidate(
    sidecar: VerifiedSidecar,
    scope_id: str,
    *,
    run_id: str = "run-1",
    work_unit_id: str = "unit-1",
) -> dict[str, object]:
    payload = {
        "runId": run_id,
        "scopeId": scope_id,
        "workUnitId": work_unit_id,
        "revision": 1,
        "files": [],
    }
    patch_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    candidate = {
        "candidateId": scope_id + "-candidate-1",
        **payload,
        "patchHash": patch_hash,
        "overlayRoot": "/host-owned-overlay",
    }
    sidecar.handle(message("candidate.attach", {"candidate": candidate}, run_id=run_id, scope_id=scope_id))
    return candidate


def failure_envelope(
    *,
    kind: str = "implementation_error",
    source_name: str = "tool",
    producer: str = "tool_host",
    scope_id: str = "root",
    action_id: str | None = None,
    message_text: str = "implementation failed",
) -> dict[str, object]:
    return {
        "version": 1,
        "id": "failure-1",
        "runId": "run-1",
        "scopeId": scope_id,
        "actionId": action_id,
        "kind": kind,
        "source": source_name,
        "producer": producer,
        "phase": "tool.execute",
        "code": "TEST_FAILURE",
        "retryable": False,
        "terminal": False,
        "classificationSource": "typed",
        "confidence": "high",
        "message": message_text,
    }


def contract(
    value: dict[str, str],
    *,
    verifier_ids: list[str] | None = None,
    risk: str = "medium",
    kind: str = "execution",
    revision: int = 1,
) -> dict[str, object]:
    ref = source_ref(value)
    return {
        "schemaVersion": "goal-contract-v2",
        "contractId": "contract-1",
        "revision": revision,
        "goal": value["text"],
        "sourceRefs": [ref],
        "criteria": [
            {
                "criterionId": "criterion-1",
                "statement": value["text"],
                "sourceRefs": [ref],
                "claimIds": ["claim-1"],
                "required": True,
                "risk": risk,
            }
        ],
        "claims": [
            {
                "claimId": "claim-1",
                "criterionIds": ["criterion-1"],
                "origin": "user",
                "statement": value["text"],
                "kind": kind,
                "scope": {
                    "targets": ["workspace"],
                    "capabilities": ["requested_behavior"],
                    "exclusions": [],
                },
                "applicability": {
                    "os": sys.platform,
                    "arch": "test",
                    "runtime": "python",
                    "provider": "test",
                    "model": "test",
                    "tools": {},
                    "dependencyLockHash": "lock",
                    "configHash": "config",
                    "workspaceRevision": "workspace-v1",
                },
                "predicate": {"type": "command_exit", "expectedExitCode": 0},
                "verifierPolicy": {
                    "minimumStrength": "execution",
                    "allowedVerifierIds": verifier_ids or ["pass"],
                    "minIndependentFamilies": 1,
                },
            }
        ],
        "constraints": ["Ready is verifier-owned."],
    }


def write_config(
    workspace: Path,
    verifiers: list[dict[str, object]],
    *,
    revoked: list[str] | None = None,
    profile: str | None = None,
) -> None:
    (workspace / "base-harness.jsonc").write_text(
        json.dumps(
            {
                "verification": {
                    **({"mode": "adaptive"} if profile is None else {"profile": profile, "trigger": "auto"}),
                    "maxSameFailureRepairs": 2,
                    "verifiers": verifiers,
                    "revokedVerifiers": revoked or [],
                }
            }
        ),
        encoding="utf-8",
    )


def verifier(
    verifier_id: str = "pass",
    *,
    exit_code: int = 0,
    method_id: str | None = None,
    strength: str = "execution",
    deterministic: bool = False,
    claim_kinds: list[str] | None = None,
    freshness_seconds: int | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "id": verifier_id,
        "command": [sys.executable, "-c", f"print('checked'); raise SystemExit({exit_code})"],
        "strength": strength,
        "claimKinds": claim_kinds or ["execution"],
        "methodId": method_id or verifier_id,
        "deterministicOracle": deterministic,
    }
    if freshness_seconds is not None:
        value["freshnessSeconds"] = freshness_seconds
    return value


def open_run(
    sidecar: VerifiedSidecar,
    workspace: Path,
    *,
    run_id: str = "run-1",
    value: dict[str, str] | None = None,
    goal_contract: dict[str, object] | None = None,
) -> dict[str, object]:
    src = value or source()
    payload: dict[str, object] = {"workspace": str(workspace), "goalSources": [src]}
    if goal_contract is not None:
        payload["goalContract"] = goal_contract
    return sidecar.handle(message("run.open", payload, run_id=run_id))


def propose_and_act(
    sidecar: VerifiedSidecar,
    workspace: Path,
    goal_contract: dict[str, object],
    *,
    run_id: str = "run-1",
    value: dict[str, str] | None = None,
) -> None:
    src = value or source()
    open_run(sidecar, workspace, run_id=run_id, value=src)
    sidecar.handle(
        message(
            "contract.propose",
            {"contract": goal_contract},
            run_id=run_id,
        )
    )
    sidecar.handle(
        message(
            "action.open",
            {
                "actionId": "action-1",
                "executionId": "execution-1",
                "claimIds": ["claim-1"],
                "tool": "write",
                "input": {"path": "result.txt"},
            },
            run_id=run_id,
        )
    )
    sidecar.handle(
        message(
            "action.close",
            {
                "actionId": "action-1",
                "status": "completed",
                "output": {"written": True},
            },
            run_id=run_id,
        )
    )


def test_protocol_v2_rejects_unrecorded_goal_source(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier()])
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    open_run(sidecar, workspace, value=src)
    forged = contract(src)
    forged["sourceRefs"][0]["sha256"] = "0" * 64  # type: ignore[index]

    with pytest.raises(ProtocolError, match="source reference"):
        sidecar.handle(message("contract.propose", {"contract": forged}))


def test_contract_requires_bidirectional_atomic_claim_binding(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier()])
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    open_run(sidecar, workspace, value=src)
    malformed = contract(src)
    malformed["criteria"][0]["claimIds"] = ["other"]  # type: ignore[index]

    with pytest.raises(ProtocolError, match="unknown claim"):
        sidecar.handle(message("contract.propose", {"contract": malformed}))


def test_action_before_contract_is_rejected_and_never_becomes_evidence(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier()])
    sidecar = VerifiedSidecar(tmp_path / "state")
    open_run(sidecar, workspace)

    result = sidecar.handle(
        message(
            "action.open",
            {
                "actionId": "early",
                "executionId": "early-execution",
                "claimIds": ["claim-1"],
                "tool": "write",
            },
        )
    )

    assert result["outcome"] == "repair"
    assert result["failedCriterion"] == "goal_contract_missing"
    assert result["candidateRefs"] == []


def test_ready_requires_bound_action_and_allowed_verifier(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(
        workspace,
        [
            verifier("pass"),
            verifier("unrelated", exit_code=7),
        ],
    )
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    goal_contract = contract(src, verifier_ids=["pass"])
    propose_and_act(sidecar, workspace, goal_contract, value=src)

    result = sidecar.handle(message("verify.request", {"reason": "manual"}))

    assert result["outcome"] == "ready"
    assert result["criterionResults"][0]["result"] == "verified"
    assert result["claimResults"][0]["coverage"] == "full"
    assert result["readyRef"]["trust"] == "verifier_attested"
    assert not str(result["readyRef"]["path"]).startswith(str(workspace))
    assert len(result["evidenceFamilies"]) == 1


def test_child_scope_verifies_claim_subset_without_ready(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier("pass")])
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    goal_contract = contract(src)
    open_run(sidecar, workspace, value=src, goal_contract=goal_contract)
    sidecar.handle(
        message(
            "scope.open",
            {
                "parentScopeId": "root",
                "kind": "work_unit",
                "assignedClaimIds": ["claim-1"],
            },
            scope_id="child",
        )
    )
    candidate = attach_candidate(sidecar, "child")
    sidecar.handle(
        message(
            "action.open",
            {
                "actionId": "child-action",
                "executionId": "child-execution",
                "claimIds": ["claim-1"],
                "tool": "write",
                "input": {"path": "result.txt"},
            },
            scope_id="child",
        )
    )
    sidecar.handle(
        message(
            "action.close",
            {
                "actionId": "child-action",
                "status": "completed",
                "output": {"written": True},
            },
            scope_id="child",
        )
    )
    child = sidecar.handle(
        message(
            "verify.request",
            {
                "reason": "completion",
                "claimIds": ["claim-1"],
                "criterionIds": ["criterion-1"],
            },
            scope_id="child",
        )
    )
    assert child["outcome"] == "scope_verified"
    assert child["scopeAttestation"]["candidateId"] == candidate["candidateId"]
    sidecar.handle(
        message(
            "candidate.commit",
            {"attestation": child["scopeAttestation"]},
            scope_id="child",
        )
    )
    assert child["readyRef"] is None
    root = sidecar.handle(message("verify.request", {"reason": "completion"}))
    assert root["outcome"] == "ready"
    assert root["configuredProfile"] == "adaptive"
    assert root["effectiveProfile"] == "adaptive"
    assert root["assuranceLevel"] == "adaptive"
    assert root["readyEligible"] is True


def test_candidate_manifest_hash_and_scope_binding_are_enforced(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier("pass")])
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    goal_contract = contract(src)
    open_run(sidecar, workspace, value=src, goal_contract=goal_contract)
    sidecar.handle(
        message(
            "scope.open",
            {"parentScopeId": "root", "kind": "work_unit", "assignedClaimIds": ["claim-1"]},
            scope_id="child",
        )
    )
    candidate = attach_candidate(sidecar, "child")
    candidate["patchHash"] = "0" * 64
    with pytest.raises(ProtocolError, match="patchHash"):
        sidecar.handle(message("candidate.attach", {"candidate": candidate}, scope_id="child"))


def test_fast_ready_records_assurance_in_status_artifact_and_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier()], profile="fast")
    state = tmp_path / "state"
    sidecar = VerifiedSidecar(state)
    src = source()
    propose_and_act(sidecar, workspace, contract(src, risk="low"), value=src)

    ready = sidecar.handle(message("verify.request", {"reason": "completion"}))

    assert ready["outcome"] == "ready"
    assert ready["configuredProfile"] == "fast"
    assert ready["effectiveProfile"] == "fast"
    assert ready["assuranceLevel"] == "fast"
    ready_artifact = json.loads(Path(ready["readyRef"]["path"]).read_text(encoding="utf-8"))
    assert ready_artifact["payload"]["assuranceLevel"] == "fast"
    manifest = json.loads(next(state.rglob("manifest.json")).read_text(encoding="utf-8"))
    assert manifest["assurance"]["assuranceLevel"] == "fast"


def test_same_failed_claim_blocks_after_two_targeted_repairs(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier(exit_code=7)])
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    propose_and_act(sidecar, workspace, contract(src), value=src)

    outcomes = [
        sidecar.handle(message("verify.request", {"reason": "automatic"}))["outcome"]
        for _ in range(3)
    ]

    assert outcomes == ["repair", "repair", "repair_exhausted"]
    assert sidecar.runs["run-1"].status == "open"


def test_high_risk_requires_independent_methods(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(
        workspace,
        [
            verifier("a", method_id="same"),
            verifier("b", method_id="same"),
        ],
    )
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    propose_and_act(
        sidecar,
        workspace,
        contract(src, verifier_ids=["a", "b"], risk="high"),
        value=src,
    )
    partial = sidecar.handle(message("verify.request", {"reason": "manual"}))
    assert partial["outcome"] == "repair"
    assert partial["claimResults"][0]["result"] == "partial"
    assert partial["effectiveProfile"] == "strict"

    workspace2 = tmp_path / "workspace-2"
    workspace2.mkdir()
    write_config(
        workspace2,
        [
            verifier("a", method_id="method-a"),
            verifier("b", method_id="method-b"),
        ],
    )
    src2 = source("Verify independent behavior")
    second = VerifiedSidecar(tmp_path / "state-2")
    propose_and_act(
        second,
        workspace2,
        contract(src2, verifier_ids=["a", "b"], risk="high"),
        value=src2,
    )
    ready = second.handle(message("verify.request", {"reason": "manual"}))
    assert ready["outcome"] == "ready"


def test_memory_reproduces_then_establishes_only_with_method_diversity(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    src = source()

    write_config(workspace, [verifier("first", method_id="method-a")])
    first = VerifiedSidecar(state)
    first_contract = contract(src, verifier_ids=["first"])
    propose_and_act(first, workspace, first_contract, run_id="run-1", value=src)
    first.handle(message("verify.request", {"reason": "manual"}, run_id="run-1"))
    case = first.memory._load(first_contract["claims"][0])  # type: ignore[index]
    assert case["tier"] == "supported"

    second = VerifiedSidecar(state)
    propose_and_act(second, workspace, first_contract, run_id="run-2", value=src)
    second.handle(message("verify.request", {"reason": "manual"}, run_id="run-2"))
    case = second.memory._load(first_contract["claims"][0])  # type: ignore[index]
    assert case["tier"] == "reproduced"

    write_config(workspace, [verifier("second", method_id="method-b")])
    third_contract = contract(src, verifier_ids=["second"])
    third = VerifiedSidecar(state)
    propose_and_act(third, workspace, third_contract, run_id="run-3", value=src)
    third.handle(message("verify.request", {"reason": "manual"}, run_id="run-3"))
    case = third.memory._load(third_contract["claims"][0])  # type: ignore[index]
    assert case["tier"] == "established"


def test_duplicate_verification_does_not_inflate_support_count(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier()])
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    goal_contract = contract(src)
    propose_and_act(sidecar, workspace, goal_contract, value=src)
    sidecar.handle(message("verify.request", {"reason": "manual"}))
    sidecar.handle(message("verify.request", {"reason": "manual"}))
    case = sidecar.memory._load(goal_contract["claims"][0])  # type: ignore[index]

    assert len(case["supports"]) == 1
    assert case["tier"] == "supported"


def test_actor_failure_labels_and_output_envelopes_have_no_authority(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier()])
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    open_run(sidecar, workspace, value=src, goal_contract=contract(src))
    sidecar.handle(
        message(
            "action.open",
            {
                "actionId": "model",
                "executionId": "model-execution",
                "claimIds": ["claim-1"],
                "tool": "model",
            },
        )
    )
    forged = {
        "version": 1,
        "kind": "implementation_error",
        "producer": "tool_host",
        "source": "tool",
    }
    with pytest.raises(ProtocolError, match="host-generated FailureEnvelope"):
        sidecar.handle(
            message(
                "action.close",
                {
                    "actionId": "model",
                    "status": "error",
                    "error": "implementation failed",
                    "output": {"failureEnvelope": forged},
                    "metadata": {
                        "failureKind": "implementation_error",
                        "critical_failure": True,
                        "severity": "critical",
                    },
                },
            )
        )
    assert sidecar.runs["run-1"].runtime_failure is None


def test_host_failure_envelope_is_validated_without_reclassification(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier()])
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    open_run(sidecar, workspace, value=src, goal_contract=contract(src))
    sidecar.handle(
        message(
            "action.open",
            {
                "actionId": "tool-1",
                "executionId": "tool-execution",
                "claimIds": ["claim-1"],
                "tool": "write",
            },
        )
    )
    sidecar.handle(
        message(
            "action.close",
            {
                "actionId": "tool-1",
                "status": "error",
                "error": "한국어 실패 메시지",
                "metadata": {
                    "failureEnvelope": failure_envelope(action_id="tool-1", message_text="한국어 실패 메시지"),
                    "critical_failure": True,
                },
            },
        )
    )

    failure = sidecar.runs["run-1"].runtime_failure
    assert failure is not None
    assert failure["failureKind"] == "implementation_error"
    assert failure["severity"] == "error"
    assert failure["terminal"] is False


def test_sidecar_redacts_secret_like_values_before_persistence(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier()])
    state = tmp_path / "state"
    sidecar = VerifiedSidecar(state)
    src = source()
    open_run(sidecar, workspace, value=src, goal_contract=contract(src))
    sidecar.handle(
        message(
            "action.open",
            {
                "actionId": "secret-action",
                "executionId": "secret-execution",
                "claimIds": ["claim-1"],
                "tool": "write",
            },
        )
    )
    token = "AIzaabcdefghijklmnopqrstuvwxyz123456"
    sidecar.handle(
        message(
            "action.close",
            {
                "actionId": "secret-action",
                "status": "completed",
                "output": {
                    "arbitrary": "Bearer abcdefghijklmnopqrstuvwxyz",
                    "GEMINI_CRED": token,
                    "비밀키": token,
                },
            },
        )
    )

    persisted = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in state.rglob("*")
        if path.is_file()
    )
    assert token not in persisted
    assert "abcdefghijklmnopqrstuvwxyz" not in persisted


def test_redact_truncates_large_strings_and_lists() -> None:
    long_text = "x" * (MAX_CAPTURE_CHARS + 500)
    redacted = redact(long_text)
    assert redacted.startswith("x")
    assert redacted.endswith("\n[TRUNCATED]")
    assert len(redacted) == MAX_CAPTURE_CHARS + len("\n[TRUNCATED]")
    redacted_list = redact(list(range(205)))
    assert redacted_list[200:] == ["[TRUNCATED]"]


def test_verifier_output_is_truncated_and_redacted_for_large_secret_output(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    token = "sk-abcdefghijklmnopqrstuvwxyz12345"
    write_config(
        workspace,
        [
            {
                "id": "long-output",
                "command": [
                    sys.executable,
                    "-c",
                    f"print('Bearer {token}')\nprint('x' * ({MAX_CAPTURE_CHARS} + 100))",
                ],
                "claimKinds": ["execution"],
                "strength": "execution",
                "contradictionSeverity": "soft",
            }
        ],
    )
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    propose_and_act(
        sidecar,
        workspace,
        contract(src, verifier_ids=["long-output"]),
        value=src,
    )
    result = sidecar.handle(message("verify.request", {"reason": "manual"}))

    evidence = json.loads(
        Path(result["evidenceRefs"][0]["path"]).read_text(encoding="utf-8")
    )["payload"]["result"]
    assert "[REDACTED]" in evidence["stdout"]
    assert "\n[TRUNCATED]" in evidence["stdout"]
    assert token not in evidence["stdout"]
    assert token not in evidence["stderr"]


def test_unknown_failure_suspends_only_its_scope_and_independent_scope_continues(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier()])
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    open_run(sidecar, workspace, value=src, goal_contract=contract(src))
    sidecar.handle(
        message(
            "action.open",
            {
                "actionId": "unknown-action",
                "executionId": "unknown-execution",
                "claimIds": ["claim-1"],
                "tool": "write",
            },
        )
    )
    unknown = failure_envelope(kind="unknown_failure", action_id="unknown-action")
    unknown["classificationSource"] = "heuristic"
    unknown["confidence"] = "low"
    unknown["retryable"] = False
    unknown.pop("code")
    sidecar.handle(
        message(
            "action.close",
            {
                "actionId": "unknown-action",
                "status": "error",
                "error": "unclassified",
                "metadata": {"failureEnvelope": unknown},
            },
        )
    )

    failure = sidecar.handle(message("verify.request", {"reason": "automatic"}))
    assert failure["outcome"] == "failure"
    assert failure["state"] == "failure"
    assert failure["repairCount"] == 0
    assert failure["repairable"] is False

    sidecar.handle(
        message(
            "scope.open",
            {
                "parentScopeId": "root",
                "kind": "work_unit",
                "assignedClaimIds": ["claim-1"],
            },
            scope_id="independent",
        )
    )
    attach_candidate(sidecar, "independent", work_unit_id="independent-unit")
    sidecar.handle(
        message(
            "action.open",
            {
                "actionId": "independent-action",
                "executionId": "independent-execution",
                "claimIds": ["claim-1"],
                "tool": "write",
            },
            scope_id="independent",
        )
    )
    sidecar.handle(
        message(
            "action.close",
            {
                "actionId": "independent-action",
                "status": "completed",
                "output": "completed",
            },
            scope_id="independent",
        )
    )
    child = sidecar.handle(
        message(
            "verify.request",
            {
                "reason": "completion",
                "claimIds": ["claim-1"],
                "criterionIds": ["criterion-1"],
            },
            scope_id="independent",
        )
    )
    assert child["outcome"] == "scope_verified"


@pytest.mark.parametrize("old_version", [1, 2, 3])
def test_old_protocol_is_fail_closed(tmp_path: Path, old_version: int) -> None:
    request = message("hello", {}, version=old_version)
    output = io.StringIO()

    assert serve(io.StringIO(json.dumps(request) + "\n"), output, VerifiedSidecar(tmp_path)) == 0
    response = json.loads(output.getvalue())
    assert response["type"] == "failure"
    assert response["payload"]["failureKind"] == "harness_protocol_version_mismatch"


def test_hard_contradiction_quarantines_case_and_removes_retrieval_projection(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier(exit_code=9)])
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    goal_contract = contract(src)
    propose_and_act(sidecar, workspace, goal_contract, value=src)

    result = sidecar.handle(message("verify.request", {"reason": "manual"}))
    case = sidecar.memory._load(goal_contract["claims"][0])  # type: ignore[index]
    projection = sidecar.memory.retrieval_root / (case["caseId"] + ".md")

    assert result["outcome"] == "repair"
    assert result["claimResults"][0]["result"] == "refuted"
    assert case["status"] == "quarantined"
    assert not projection.exists()


def test_revoked_verifier_recomputes_and_quarantines_dependent_case(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    src = source()
    goal_contract = contract(src)
    write_config(workspace, [verifier()])
    first = VerifiedSidecar(state)
    propose_and_act(first, workspace, goal_contract, value=src)
    assert first.handle(message("verify.request", {"reason": "manual"}))["outcome"] == "ready"

    write_config(workspace, [verifier()], revoked=["pass"])
    second = VerifiedSidecar(state)
    propose_and_act(second, workspace, goal_contract, run_id="run-2", value=src)
    result = second.handle(message("verify.request", {"reason": "manual"}, run_id="run-2"))
    case = second.memory._load(goal_contract["claims"][0])  # type: ignore[index]

    assert result["outcome"] == "failure"
    assert result["failureKind"] == "verifier_error"
    assert result["repairCount"] == 0
    assert result["repairable"] is False
    assert result["claimResults"][0]["result"] == "verifier_invalid"
    assert case["tier"] == "candidate"
    assert case["status"] == "quarantined"


def test_applicability_change_creates_separate_case_without_demoting_original(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier()])
    state = tmp_path / "state"
    src = source()
    original_contract = contract(src)
    first = VerifiedSidecar(state)
    propose_and_act(first, workspace, original_contract, value=src)
    first.handle(message("verify.request", {"reason": "manual"}))
    original_claim = original_contract["claims"][0]  # type: ignore[index]
    original_case = first.memory._load(original_claim)

    changed_contract = contract(src)
    changed_contract["claims"][0]["applicability"]["configHash"] = "config-v2"  # type: ignore[index]
    changed_claim = changed_contract["claims"][0]  # type: ignore[index]

    assert first.memory.case_id(original_claim) != first.memory.case_id(changed_claim)
    assert original_case["tier"] == "supported"


def test_expired_evidence_cannot_supply_historical_independence(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier(freshness_seconds=1)])
    state = tmp_path / "state"
    src = source()
    goal_contract = contract(src)
    sidecar = VerifiedSidecar(state)
    propose_and_act(sidecar, workspace, goal_contract, value=src)
    sidecar.handle(message("verify.request", {"reason": "manual"}))
    claim = goal_contract["claims"][0]  # type: ignore[index]
    case = sidecar.memory._load(claim)
    case["supports"][0]["observedAt"] = "2000-01-01T00:00:00+00:00"
    case_path = sidecar.memory.case_root / (case["caseId"] + ".json")
    case_path.write_text(json.dumps(case), encoding="utf-8")

    methods = sidecar.memory.independent_historical_methods(claim, set(), set())

    assert methods == set()


def test_current_soft_counterevidence_prevents_ready_even_with_support(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    counter = verifier("counter", exit_code=1)
    counter["contradictionSeverity"] = "soft"
    write_config(workspace, [verifier("support"), counter])
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    goal_contract = contract(src, verifier_ids=["support", "counter"])
    propose_and_act(sidecar, workspace, goal_contract, value=src)

    result = sidecar.handle(message("verify.request", {"reason": "manual"}))
    assert result["outcome"] == "repair"
    assert result["readyEligible"] is False
    assert result["claimResults"][0]["result"] == "refuted"
    assert len(result["claimResults"][0]["evidenceIds"]) == 2
    assert all(item["status"] == "disputed" for item in result["evidenceFamilies"])
    assert result["readyRef"] is None


@pytest.mark.parametrize(
    ("freshness_seconds", "expected_methods"),
    [(None, set()), (3600, {"pass"})],
    ids=["missing-freshness", "fresh-evidence"],
)
def test_disputed_history_cannot_supply_missing_independence(
    tmp_path: Path,
    freshness_seconds: int | None,
    expected_methods: set[str],
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_config(workspace, [verifier(freshness_seconds=freshness_seconds)])
    sidecar = VerifiedSidecar(tmp_path / "state")
    src = source()
    goal_contract = contract(src)
    propose_and_act(sidecar, workspace, goal_contract, value=src)
    assert sidecar.handle(message("verify.request", {}))["outcome"] == "ready"
    claim = goal_contract["claims"][0]
    case = sidecar.memory._load(claim)
    assert case["status"] == "active"
    # Current verification can succeed without authorizing historical reuse.
    assert sidecar.memory.independent_historical_methods(claim, set(), set()) == expected_methods
    counter = dict(case["supports"][0])
    counter.update({"evidenceId": "counter-evidence", "semanticFingerprint": "counter-fingerprint",
                    "familyId": "counter-family"})
    sidecar.memory.record(claim, counter, support=False, severity="soft")
    assert sidecar.memory._load(claim)["status"] == "disputed"
    assert sidecar.memory.independent_historical_methods(claim, set(), set()) == set()
