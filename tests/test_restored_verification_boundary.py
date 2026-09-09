"""Regression tests for restored independent verification boundaries."""
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.verification_v2 import ProtocolError, VerificationEngine, canonical_hash


@pytest.fixture(autouse=True)
def isolated_configuration(tmp_path, monkeypatch):
    for name in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / "configuration"))


def open_harness(tmp_path, predicates=None, verifier=None):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    if verifier:
        (workspace / "base-harness.jsonc").write_text(
            json.dumps({"verification": {"verifiers": [verifier]}}), encoding="utf-8"
        )
    engine = VerificationEngine(tmp_path / "state")
    goal = "Produce the requested artifacts"
    source = {"sourceId": "request", "sourceType": "user_message", "text": goal}
    ref = {"sourceId": "request", "sourceType": "user_message",
           "sha256": hashlib.sha256(goal.encode()).hexdigest()}

    def call(kind, payload=None, scope="root"):
        return engine.handle({
            "version": 4, "id": kind, "runId": "test-run",
            "scopeId": scope, "type": kind, "payload": payload or {},
        })

    call("run.open", {"workspace": str(workspace), "goalSources": [source]})
    predicates = predicates or [{"type": "content_equals", "value": "expected\n"}]
    claims, criteria = [], []
    for index, predicate in enumerate(predicates):
        cid, criterion = "claim-" + str(index), "criterion-" + str(index)
        claims.append({
            "claimId": cid, "criterionIds": [criterion], "origin": "user",
            "statement": "Check artifact " + str(index),
            "kind": "execution" if verifier else "artifact",
            "scope": {"targets": ["result-" + str(index) + ".txt"],
                      "capabilities": ["write"], "exclusions": []},
            "applicability": {
                "os": sys.platform, "arch": "test", "runtime": sys.version,
                "provider": "fixture", "model": "fixture", "tools": {},
                "dependencyLockHash": "fixture", "configHash": "fixture",
                "workspaceRevision": str(tmp_path),
            },
            "predicate": predicate,
            "verifierPolicy": {
                "minimumStrength": "execution" if verifier else "structural",
                "allowedVerifierIds": [verifier["id"] if verifier else "file"],
                "minIndependentFamilies": 1,
            },
        })
        criteria.append({
            "criterionId": criterion, "statement": "Check " + str(index),
            "claimIds": [cid], "sourceRefs": [ref], "required": True, "risk": "low",
        })
    contract = {
        "schemaVersion": "goal-contract-v2", "contractId": "contract-test",
        "revision": 1, "goal": goal, "sourceRefs": [ref],
        "criteria": criteria, "claims": claims, "constraints": [],
    }
    return engine, workspace, call, contract


def observe(call, claims=("claim-0",), scope="root", action="action"):
    call("action.open", {
        "actionId": action, "executionId": action, "claimIds": list(claims),
        "tool": "fixture", "input": {"target": "artifact"},
    }, scope)
    call("action.close", {
        "actionId": action, "status": "completed",
        "output": {"outcome": "ready", "scope_verified": True, "fileExists": True},
    }, scope)


def attach(engine, workspace, call, contents, scope="child"):
    directory = engine.state_root / "candidate-workspace"
    directory.mkdir(exist_ok=True)
    target = directory / "result-0.txt"
    target.write_bytes(contents.encode("utf-8"))
    original = workspace / "result-0.txt"
    files = [{
        "path": str(original),
        "beforeHash": hashlib.sha256(original.read_bytes()).hexdigest() if original.exists() else None,
        "afterHash": hashlib.sha256(target.read_bytes()).hexdigest(),
    }]
    binding = {
        "runId": "test-run", "scopeId": scope, "workUnitId": "unit",
        "revision": 1, "files": files,
    }
    manifest = {
        **binding, "candidateId": "candidate",
        "patchHash": canonical_hash(binding), "overlayRoot": str(directory),
        "candidateWorkspace": str(directory),
    }
    call("candidate.attach", {"candidate": manifest}, scope)
    return manifest


def test_file_claim_ignores_actor_success_then_accepts_real_repair(tmp_path):
    engine, workspace, call, contract = open_harness(tmp_path)
    assert call("contract.propose", {"contract": contract})["contractStatus"] == "accepted"
    observe(call)
    failed = call("verify.request")
    assert failed["outcome"] == "repair"
    assert not failed["readyEligible"]
    (workspace / "result-0.txt").write_bytes(b"expected\n")
    observe(call, action="repair")
    ready = call("verify.request")
    assert ready["outcome"] == "ready"
    assert ready["claimResults"][0]["coverage"] == "full"
    assert ready["readyRef"]["trust"] == "verifier_attested"
    evidence = json.loads(Path(ready["evidenceRefs"][-1]["path"]).read_text(encoding="utf-8"))
    assert "expected\n" not in json.dumps(evidence)


@pytest.mark.parametrize("predicate", [
    {"type": "exists"},
    {"type": "content_contains", "value": "expected"},
    {"type": "content_equals", "value": "expected\n"},
    {"type": "sha256", "value": hashlib.sha256(b"expected\n").hexdigest()},
])
def test_independent_file_predicates(tmp_path, predicate):
    _, workspace, call, contract = open_harness(tmp_path, [predicate])
    call("contract.propose", {"contract": contract})
    (workspace / "result-0.txt").write_bytes(b"expected\n")
    observe(call)
    assert call("verify.request")["outcome"] == "ready"


@pytest.mark.parametrize("predicate", [
    {"type": "command_exit", "expectedExitCode": 0},
    {"type": "content_contains", "value": ""},
    {"type": "sha256", "value": "not-a-digest"},
])
def test_file_verifier_rejects_incompatible_predicate(tmp_path, predicate):
    _, _, call, contract = open_harness(tmp_path, [predicate])
    with pytest.raises(ProtocolError):
        call("contract.propose", {"contract": contract})


def test_file_claim_cannot_escape_workspace_or_overstate_strength(tmp_path):
    _, _, call, contract = open_harness(tmp_path)
    contract["claims"][0]["scope"]["targets"] = ["../outside.txt"]
    with pytest.raises(ProtocolError, match="inside the workspace"):
        call("contract.propose", {"contract": contract})
    contract["claims"][0]["scope"]["targets"] = ["result-0.txt"]
    contract["claims"][0]["verifierPolicy"]["minimumStrength"] = "behavioral"
    with pytest.raises(ProtocolError, match="strong enough"):
        call("contract.propose", {"contract": contract})


@pytest.mark.parametrize("selection", [
    {"claimIds": ["claim-0"]},
    {"criterionIds": ["criterion-0"]},
    {"criterionIds": ["invented"]},
])
def test_root_cannot_issue_ready_for_a_subset(tmp_path, selection):
    _, _, call, contract = open_harness(tmp_path, [{"type": "exists"}, {"type": "exists"}])
    call("contract.propose", {"contract": contract})
    observe(call, ["claim-0", "claim-1"])
    with pytest.raises(ProtocolError):
        call("verify.request", selection)
    assert not call("status.get")["readyEligible"]


def test_child_cannot_verify_unassigned_claim(tmp_path):
    _, _, call, contract = open_harness(tmp_path, [{"type": "exists"}, {"type": "exists"}])
    call("contract.propose", {"contract": contract})
    call("scope.open", {"parentScopeId": "root", "kind": "integration",
                        "assignedClaimIds": ["claim-0"]}, "child")
    with pytest.raises(ProtocolError, match="assigned Claims"):
        call("verify.request", {"claimIds": ["claim-1"]}, "child")


def test_one_command_observation_is_shared_without_reexecution(tmp_path):
    command = [
        sys.executable, "-c",
        "from pathlib import Path; p=Path('count'); "
        "p.write_text(str(int(p.read_text())+1) if p.exists() else '1'); print('ok')",
    ]
    verifier = {"id": "counter", "command": command, "claimKinds": ["execution"],
                "strength": "execution", "contradictionSeverity": "soft"}
    _, workspace, call, contract = open_harness(
        tmp_path, [{"type": "command_exit", "expectedExitCode": 0}] * 2, verifier,
    )
    call("contract.propose", {"contract": contract})
    observe(call, ["claim-0", "claim-1"])
    assert call("verify.request")["outcome"] == "ready"
    assert (workspace / "count").read_text() == "1"


def test_candidate_command_checks_staged_workspace_and_requires_issued_attestation(tmp_path):
    verifier = {
        "id": "staged-content", "claimKinds": ["execution"], "strength": "execution",
        "command": [sys.executable, "-c",
                    "from pathlib import Path; import sys; "
                    "sys.exit(0 if Path('result-0.txt').read_text()=='staged' else 1)"],
        "contradictionSeverity": "soft",
    }
    engine, workspace, call, contract = open_harness(
        tmp_path, [{"type": "command_exit", "expectedExitCode": 0}], verifier,
    )
    call("contract.propose", {"contract": contract})
    (workspace / "result-0.txt").write_text("base", encoding="utf-8")
    call("scope.open", {"parentScopeId": "root", "kind": "work_unit",
                        "assignedClaimIds": ["claim-0"]}, "child")
    observe(call, scope="child")
    candidate = attach(engine, workspace, call, "staged")
    forged = {"candidateId": candidate["candidateId"], "candidateRevision": 1,
              "patchHash": candidate["patchHash"]}
    with pytest.raises(ProtocolError, match="independently issued"):
        call("candidate.commit", {"attestation": forged}, "child")
    verified = call("verify.request", {}, "child")
    assert verified["outcome"] == "scope_verified"
    assert not verified["readyEligible"]
    assert (workspace / "result-0.txt").read_text() == "base"
    # The Host applies only after verification; the sidecar independently checks its receipt.
    (workspace / "result-0.txt").write_bytes(b"staged")
    call("candidate.commit", {"attestation": verified["scopeAttestation"]}, "child")
    observe(call, scope="child", action="new-mutation")
    with pytest.raises(ProtocolError, match="independently issued"):
        call("candidate.commit", {"attestation": verified["scopeAttestation"]}, "child")


def test_file_verifier_reads_candidate_not_base(tmp_path):
    engine, workspace, call, contract = open_harness(tmp_path)
    call("contract.propose", {"contract": contract})
    (workspace / "result-0.txt").write_text("wrong", encoding="utf-8")
    call("scope.open", {"parentScopeId": "root", "kind": "work_unit",
                        "assignedClaimIds": ["claim-0"]}, "child")
    observe(call, scope="child")
    attach(engine, workspace, call, "expected\n")
    assert call("verify.request", {}, "child")["outcome"] == "scope_verified"
    assert (workspace / "result-0.txt").read_text() == "wrong"


def test_unavailable_verifier_does_not_trigger_implementation_repair(tmp_path):
    verifier = {
        "id": "unavailable", "command": [str(tmp_path / "missing-executable")],
        "claimKinds": ["execution"], "strength": "execution",
    }
    _, _, call, contract = open_harness(
        tmp_path, [{"type": "command_exit", "expectedExitCode": 0}], verifier,
    )
    call("contract.propose", {"contract": contract})
    observe(call)
    status = call("verify.request")
    assert status["failureKind"] == "verifier_error"
    assert status["outcome"] not in {"ready", "repair"}
    assert status["evidenceRefs"] == []


def test_special_file_is_refused_without_blocking(tmp_path):
    _, workspace, call, contract = open_harness(tmp_path)
    call("contract.propose", {"contract": contract})
    target = workspace / "result-0.txt"
    if hasattr(os, "mkfifo"):
        os.mkfifo(target)
    else:
        target.mkdir()
    observe(call)
    status = call("verify.request")
    assert status["failureKind"] == "verifier_error"
    assert not status["readyEligible"]


@pytest.mark.parametrize("kind,producer,source", [
    ("model_provider_error", "model_gateway", "provider"),
    ("model_protocol_error", "model_gateway", "model"),
    ("workspace_conflict", "orchestrator", "workspace"),
    ("verifier_error", "verifier_sidecar", "verifier"),
    ("harness_error", "orchestrator", "harness"),
    ("unknown_failure", "orchestrator", "harness"),
])
def test_boundary_failures_do_not_consume_code_repairs(tmp_path, kind, producer, source):
    _, _, call, contract = open_harness(tmp_path)
    call("contract.propose", {"contract": contract})
    call("action.open", {
        "actionId": "failed-action", "executionId": "failed-execution",
        "claimIds": ["claim-0"], "tool": "fixture",
    })
    unknown = kind == "unknown_failure"
    envelope = {
        "version": 1, "id": "failure-id", "runId": "test-run", "scopeId": "root",
        "actionId": "failed-action", "kind": kind, "producer": producer, "source": source,
        "phase": "execution", "code": "FIXTURE_ERROR", "retryable": False,
        "terminal": True, "classificationSource": "heuristic" if unknown else "typed",
        "confidence": "low" if unknown else "high", "message": "Fixture boundary failure",
    }
    call("action.close", {
        "actionId": "failed-action", "status": "error", "error": "Fixture boundary failure",
        "metadata": {"failureEnvelope": envelope},
    })
    for _ in range(3):
        status = call("verify.request")
        assert status["outcome"] == "failure"
        assert status["failureKind"] == kind
        assert status["repairCount"] == 0
        assert not status["repairable"]
        assert not status["readyEligible"]


def prepared_child(tmp_path, verifier=None, predicate=None):
    engine, workspace, call, contract = open_harness(
        tmp_path, [predicate] if predicate else None, verifier,
    )
    call("contract.propose", {"contract": contract})
    (workspace / "result-0.txt").write_bytes(b"before")
    call("scope.open", {"parentScopeId": "root", "kind": "work_unit",
                       "assignedClaimIds": ["claim-0"]}, "child")
    observe(call, scope="child")
    candidate = attach(engine, workspace, call, "expected\n")
    return engine, workspace, call, candidate


@pytest.mark.parametrize("target", ["candidate", "base"])
def test_changed_candidate_or_base_never_produces_evidence(tmp_path, target):
    _, workspace, call, candidate = prepared_child(tmp_path)
    directory = Path(candidate["candidateWorkspace"]) if target == "candidate" else workspace
    (directory / "result-0.txt").write_bytes(b"tampered")
    rejected = call("verify.request", {}, "child")
    assert rejected["failureKind"] == "workspace_conflict"
    assert rejected["outcome"] == "failure"
    assert rejected["repairCount"] == 0
    assert rejected["evidenceRefs"] == []
    assert not rejected.get("scopeAttestation")
    assert not rejected["readyEligible"]
    assert ("afterHash" if target == "candidate" else "beforeHash") in rejected["missingEvidence"][0]


def test_verifier_mutation_is_detected_before_evidence_promotion(tmp_path):
    verifier = {
        "id": "mutating", "claimKinds": ["execution"], "strength": "execution",
        "command": [sys.executable, "-c",
                    "from pathlib import Path; Path('result-0.txt').write_bytes(b'changed'); print('ok')"],
    }
    _, workspace, call, candidate = prepared_child(
        tmp_path, verifier, {"type": "command_exit", "expectedExitCode": 0},
    )
    rejected = call("verify.request", {}, "child")
    assert rejected["failureKind"] == "workspace_conflict"
    assert rejected["evidenceRefs"] == []
    assert rejected["repairCount"] == 0
    assert (workspace / "result-0.txt").read_bytes() == b"before"
    assert (Path(candidate["candidateWorkspace"]) / "result-0.txt").read_bytes() == b"changed"


def test_nonempty_candidate_cannot_fall_back_to_the_original_workspace(tmp_path):
    _, workspace, call, candidate = prepared_child(tmp_path)
    candidate.pop("candidateWorkspace")
    call("candidate.attach", {"candidate": candidate}, "child")
    rejected = call("verify.request", {}, "child")
    assert rejected["failureKind"] == "workspace_conflict"
    assert rejected["evidenceRefs"] == []
    assert (workspace / "result-0.txt").read_bytes() == b"before"


@pytest.mark.parametrize("change", ["duplicate", "outside"])
def test_candidate_manifest_rejects_duplicate_and_outside_paths(tmp_path, change):
    _, workspace, call, candidate = prepared_child(tmp_path)
    if change == "duplicate":
        candidate["files"].append(dict(candidate["files"][0]))
    else:
        candidate["files"][0]["path"] = str(workspace.parent / "outside.txt")
    payload = {key: candidate[key] for key in ("runId", "scopeId", "workUnitId", "revision")}
    payload["files"] = sorted(candidate["files"], key=lambda item: item["path"])
    candidate["patchHash"] = canonical_hash(payload)
    with pytest.raises(ProtocolError, match="duplicate|escapes"):
        call("candidate.attach", {"candidate": candidate}, "child")


def test_candidate_commit_requires_actual_matching_workspace_bytes(tmp_path):
    _, workspace, call, _ = prepared_child(tmp_path)
    verified = call("verify.request", {}, "child")
    assert verified["outcome"] == "scope_verified"
    result = call("candidate.commit", {"attestation": verified["scopeAttestation"]}, "child")
    assert result["failureKind"] == "workspace_conflict"
    assert result["outcome"] == "failure"
    assert result["repairCount"] == 0
    assert (workspace / "result-0.txt").read_bytes() == b"before"


def test_candidate_evidence_carries_binding_and_commit_attestation_is_single_use(tmp_path):
    _, workspace, call, candidate = prepared_child(tmp_path)
    verified = call("verify.request", {}, "child")
    evidence = json.loads(Path(verified["evidenceRefs"][-1]["path"]).read_text(encoding="utf-8"))
    assert evidence["payload"]["candidateBinding"]["patchHash"] == candidate["patchHash"]
    assert evidence["payload"]["candidateBinding"]["observedFiles"][0]["sha256"] == candidate["files"][0]["afterHash"]
    (workspace / "result-0.txt").write_bytes(b"expected\n")
    committed = call("candidate.commit", {"attestation": verified["scopeAttestation"]}, "child")
    assert committed["committedCandidate"]["patchHash"] == candidate["patchHash"]
    with pytest.raises(ProtocolError, match="independently issued"):
        call("candidate.commit", {"attestation": verified["scopeAttestation"]}, "child")


def test_candidate_ctime_is_compared_with_the_same_metadata_accessor(tmp_path, monkeypatch):
    _, _, call, _ = prepared_child(tmp_path)
    original = os.fstat

    def descriptor_stat(descriptor):
        value = original(descriptor)
        fields = {key: getattr(value, key) for key in (
            "st_mode", "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink",
        )}
        fields["st_ctime_ns"] += 1_000_000
        return SimpleNamespace(**fields)

    monkeypatch.setattr(os, "fstat", descriptor_stat)
    verified = call("verify.request", {}, "child")
    assert verified["outcome"] == "scope_verified"


def test_candidate_still_detects_descriptor_ctime_changes_during_a_read(tmp_path, monkeypatch):
    _, _, call, _ = prepared_child(tmp_path)
    original = os.fstat
    calls = 0

    def descriptor_stat(descriptor):
        nonlocal calls
        calls += 1
        value = original(descriptor)
        fields = {key: getattr(value, key) for key in (
            "st_mode", "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink",
        )}
        if calls == 2:
            fields["st_ctime_ns"] += 1_000_000
        return SimpleNamespace(**fields)

    monkeypatch.setattr(os, "fstat", descriptor_stat)
    rejected = call("verify.request", {}, "child")
    assert rejected["failureKind"] == "workspace_conflict"
    assert "while being independently read" in rejected["missingEvidence"][0]
    assert rejected["evidenceRefs"] == []


def scoped_candidate(engine, workspace, call, index, scope, contents, revision=1):
    directory = engine.state_root / scope / str(revision)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / ("result-" + str(index) + ".txt")
    target.write_text(contents, encoding="utf-8")
    original = workspace / target.name
    binding = {
        "runId": "test-run", "scopeId": scope, "workUnitId": scope,
        "revision": revision, "files": [{
            "path": str(original),
            "beforeHash": hashlib.sha256(original.read_bytes()).hexdigest() if original.exists() else None,
            "afterHash": hashlib.sha256(target.read_bytes()).hexdigest(),
        }],
    }
    manifest = {
        **binding, "candidateId": scope + "-" + str(revision),
        "patchHash": canonical_hash(binding), "overlayRoot": str(directory),
        "candidateWorkspace": str(directory),
    }
    call("candidate.attach", {"candidate": manifest}, scope)
    return manifest


def two_scopes(tmp_path):
    engine, workspace, call, contract = open_harness(
        tmp_path, [{"type": "content_equals", "value": "expected"}] * 2,
    )
    call("contract.propose", {"contract": contract})
    for index in range(2):
        (workspace / ("result-" + str(index) + ".txt")).write_text("before", encoding="utf-8")
        call("scope.open", {"parentScopeId": "root", "kind": "work_unit",
                            "assignedClaimIds": ["claim-" + str(index)]}, "child-" + str(index))
    return engine, workspace, call


def test_child_rejection_isolated_and_reopen_clears_only_its_scope(tmp_path):
    engine, workspace, call = two_scopes(tmp_path)
    observe(call, ["claim-0"], "child-0")
    scoped_candidate(engine, workspace, call, 0, "child-0", "wrong")
    rejected = call("verify.request", {}, "child-0")
    assert rejected["outcome"] == "repair"
    assert rejected["failureKind"] == "implementation_error"
    assert call("status.get", {}, "child-0")["outcome"] == "repair"
    assert call("status.get", {}, "child-1")["outcome"] is None
    assert call("status.get")["readyEligible"] is False
    observe(call, ["claim-1"], "child-1")
    scoped_candidate(engine, workspace, call, 1, "child-1", "expected")
    sibling = call("verify.request", {}, "child-1")
    assert sibling["outcome"] == "scope_verified"
    assert sibling["readyRef"] is None
    assert not sibling["readyEligible"]
    opened = call("scope.reopen", {}, "child-0")
    assert opened["outcome"] is None
    assert opened["failureKind"] is None
    assert opened["failedCriterion"] is None
    observe(call, ["claim-0"], "child-0", "repair")
    scoped_candidate(engine, workspace, call, 0, "child-0", "expected", revision=2)
    repaired = call("verify.request", {}, "child-0")
    assert repaired["outcome"] == "scope_verified"
    for index, result in [(0, repaired), (1, sibling)]:
        (workspace / ("result-" + str(index) + ".txt")).write_text("expected", encoding="utf-8")
        call("candidate.commit", {"attestation": result["scopeAttestation"]}, "child-" + str(index))
    ready = call("verify.request")
    assert ready["outcome"] == "ready"
    assert all(item["result"] == "verified" for item in ready["criterionResults"])


def test_scope_exhaustion_keeps_its_budget_and_does_not_stop_a_sibling(tmp_path):
    engine, workspace, call = two_scopes(tmp_path)
    outcomes = []
    for revision in range(1, 4):
        if revision > 1:
            call("scope.reopen", {}, "child-0")
        observe(call, ["claim-0"], "child-0", "attempt-" + str(revision))
        scoped_candidate(engine, workspace, call, 0, "child-0", "wrong", revision)
        status = call("verify.request", {}, "child-0")
        outcomes.append(status["outcome"])
    assert outcomes == ["repair", "repair", "repair_exhausted"]
    assert status["repairCount"] == 2
    assert status["rejectionCount"] == 3
    with pytest.raises(ProtocolError, match="remaining budget"):
        call("scope.reopen", {}, "child-0")
    observe(call, ["claim-1"], "child-1")
    scoped_candidate(engine, workspace, call, 1, "child-1", "expected")
    sibling = call("verify.request", {}, "child-1")
    assert sibling["outcome"] == "scope_verified"
    assert call("status.get", {}, "child-0")["outcome"] == "repair_exhausted"
    assert not call("status.get")["readyEligible"]
    scopes = engine.runs["test-run"].scopes
    assert list(scopes["child-0"].repair_counts.values()) == [3]
    assert scopes["child-1"].repair_counts == {}


def scoped_error(call, index, kind):
    scope, action = "child-" + str(index), "error-" + str(index)
    provider = kind == "model_provider_error"
    unknown = kind == "unknown_failure"
    call("action.open", {
        "actionId": action, "executionId": action, "claimIds": ["claim-" + str(index)], "tool": "fixture",
    }, scope)
    envelope = {
        "version": 1, "id": action, "runId": "test-run", "scopeId": scope, "actionId": action,
        "kind": kind, "source": "provider" if provider else "tool",
        "producer": "model_gateway" if provider else "tool_host", "phase": "fixture.execute",
        "code": "FIXTURE_FAILURE", "retryable": False, "terminal": False,
        "classificationSource": "heuristic" if unknown else "typed",
        "confidence": "low" if unknown else "high", "message": "fixture failure",
    }
    call("action.close", {
        "actionId": action, "status": "error", "error": envelope,
        "metadata": {"failureEnvelope": envelope},
    }, scope)


def test_runtime_failures_are_scope_local_and_root_checks_all_unresolved_failures(tmp_path):
    engine, workspace, call = two_scopes(tmp_path)
    for index in range(2):
        scoped_candidate(engine, workspace, call, index, "child-" + str(index), "expected")
    scoped_error(call, 0, "tool_execution_error")
    scoped_error(call, 1, "model_provider_error")
    assert call("verify.request", {}, "child-0")["failureKind"] == "tool_execution_error"
    assert call("verify.request", {}, "child-1")["failureKind"] == "model_provider_error"
    root = call("verify.request")
    assert root["failureKind"] == "model_provider_error"
    assert not root["repairable"]
    call("scope.reopen", {}, "child-0")
    assert engine.runs["test-run"].scopes["child-0"].runtime_failure is None
    assert engine.runs["test-run"].scopes["child-1"].runtime_failure is not None
    root = call("verify.request")
    assert root["failureKind"] == "model_provider_error"
    assert root["repairScopeId"] == "child-1"
    assert not root["readyEligible"]


def test_child_status_never_inherits_root_ready_authority(tmp_path):
    _, workspace, call, contract = open_harness(tmp_path)
    call("contract.propose", {"contract": contract})
    (workspace / "result-0.txt").write_bytes(b"expected\n")
    observe(call)
    assert call("verify.request")["outcome"] == "ready"
    child = call("scope.open", {"parentScopeId": "root", "kind": "work_unit",
                                "assignedClaimIds": ["claim-0"]}, "child")
    assert child["state"] == "open"
    assert child["outcome"] is None
    assert child["readyRef"] is None
    assert not child["readyEligible"]


def test_nonrepairable_reopen_and_child_run_close_are_denied(tmp_path):
    engine, workspace, call = two_scopes(tmp_path)
    scoped_candidate(engine, workspace, call, 0, "child-0", "expected")
    scoped_error(call, 0, "unknown_failure")
    result = call("verify.request", {}, "child-0")
    assert result["repairCount"] == 0
    assert not result["repairable"]
    with pytest.raises(ProtocolError, match="repairable rejection"):
        call("scope.reopen", {}, "child-0")
    with pytest.raises(ProtocolError, match="root scope"):
        call("run.close", {}, "child-0")
    call("run.close")
    with pytest.raises(ProtocolError, match="run is closed"):
        call("action.open", {}, "child-1")


def test_repaired_observation_is_active_without_erasing_disputed_case(tmp_path):
    engine, workspace, call, contract = open_harness(tmp_path)
    call("contract.propose", {"contract": contract})
    observe(call)
    rejected = call("verify.request")
    assert rejected["outcome"] == "repair"
    assert rejected["evidenceFamilies"][0]["status"] == "disputed"
    old_reference = rejected["evidenceRefs"][-1]
    old_evidence = json.loads(Path(old_reference["path"]).read_text(encoding="utf-8"))
    assert old_evidence["payload"]["verified"] is False

    (workspace / "result-0.txt").write_bytes(b"expected\n")
    observe(call, action="repair")
    accepted = call("verify.request")
    assert accepted["outcome"] == "ready"
    selected = accepted["claimResults"][0]
    family = next(item for item in accepted["evidenceFamilies"]
                  if item["claimId"] == "claim-0" and item["familyId"] in selected["familyIds"])
    assert family["status"] == "active"
    assert family["statusScope"] == "verification_observation"
    assert family["memoryCaseStatus"] == "disputed"
    assert family["evidenceIds"] == selected["evidenceIds"]
    assert len(accepted["evidenceFamilies"]) == 1
    assert old_reference in accepted["evidenceRefs"]
    case = engine.memory._load(contract["claims"][0])
    assert case["status"] == "disputed"
    assert len(case["contradictions"]) == 1


def test_shared_method_retains_each_claim_family_association(tmp_path):
    verifier = {
        "id": "shared", "command": [sys.executable, "-c", "raise SystemExit(0)"],
        "claimKinds": ["execution"], "strength": "execution", "contradictionSeverity": "soft",
    }
    _, _, call, contract = open_harness(
        tmp_path, [{"type": "command_exit", "expectedExitCode": 0}] * 2, verifier,
    )
    call("contract.propose", {"contract": contract})
    observe(call, ["claim-0", "claim-1"])
    result = call("verify.request")
    assert result["outcome"] == "ready"
    families = result["evidenceFamilies"]
    assert {item["claimId"] for item in families} == {"claim-0", "claim-1"}
    assert len({item["familyId"] for item in families}) == 1
    for claim in result["claimResults"]:
        family = next(item for item in families if item["claimId"] == claim["claimId"])
        assert family["status"] == "active"
        assert family["evidenceIds"] == claim["evidenceIds"]
