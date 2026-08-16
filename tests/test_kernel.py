import pytest
from harness.core.state import HarnessState, Claim, ClaimStatus, Authority
from harness.core.failures import FailureRouter, Failure, FailureKind, RecoveryAction
from harness.core.verification import EvidenceRefVerifier

def test_unverified_cannot_commit():
    state = HarnessState()
    with pytest.raises(ValueError):
        state.commit_verified(Claim("x", 1))

def test_verified_can_commit():
    state = HarnessState()
    claim = Claim("x", 1, ClaimStatus.VERIFIED, Authority.TRUSTED_TOOL)
    state.commit_verified(claim)
    assert state.facts["x"].value == 1

def test_state_round_trip():
    state = HarnessState()
    state.propose(Claim("x", {"a": 1}, evidence_refs=["a.json"]))
    restored = HarnessState.from_snapshot(state.snapshot())
    assert restored.hypotheses["x"].value == {"a": 1}
    assert restored.hypotheses["x"].evidence_refs == ["a.json"]

def test_failure_router_escalates_repeated_signature():
    router = FailureRouter(repeat_limit=3)
    failure = Failure(FailureKind.TOOL_ERROR, "timeout after 10 seconds", "shell")
    assert router.route(failure, 1) == RecoveryAction.REPAIR
    assert router.route(failure, 3) == RecoveryAction.SWITCH_STRATEGY

def test_evidence_ref_verifier_rejects_unresolved_ref():
    verifier = EvidenceRefVerifier()
    result = verifier.verify(1, {"claim_evidence_refs": ["missing"], "state": {"artifacts": []}})
    assert not result.verified
