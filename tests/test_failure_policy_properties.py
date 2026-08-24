import pytest

from harness.core.failures import (
    FailureContext,
    FailureKind,
    FailureOrigin,
    FailurePhase,
    FailurePolicyEngine,
    RecoveryAction,
)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (FailureKind.MODEL_PROTOCOL_ERROR, RecoveryAction.REPAIR),
        (FailureKind.MODEL_PROVIDER_ERROR, RecoveryAction.OBSERVE),
        (FailureKind.ACTOR_WORKFLOW_ERROR, RecoveryAction.REPLAN),
        (FailureKind.IMPLEMENTATION_ERROR, RecoveryAction.REPAIR),
        (FailureKind.PERSISTENCE_ERROR, RecoveryAction.CHECKPOINT_STOP),
        (FailureKind.SECURITY_VIOLATION, RecoveryAction.CHECKPOINT_STOP),
        (FailureKind.TOOL_ERROR, RecoveryAction.REPAIR),
        (FailureKind.MISSING_INFO, RecoveryAction.OBSERVE),
    ],
)
def test_failure_domain_routes_are_stable(kind, expected):
    origin = FailureOrigin.HARNESS
    phase = FailurePhase.RECOVERY
    if kind is FailureKind.MODEL_PROTOCOL_ERROR:
        origin, phase = FailureOrigin.MODEL, FailurePhase.PROTOCOL_VALIDATE
    elif kind is FailureKind.MODEL_PROVIDER_ERROR:
        origin, phase = FailureOrigin.PROVIDER, FailurePhase.PROVIDER_CALL
    elif kind is FailureKind.ACTOR_WORKFLOW_ERROR:
        origin, phase = FailureOrigin.MODEL, FailurePhase.WORKFLOW
    context = FailureContext(kind=kind, origin=origin, phase=phase, message="probe")
    decision = FailurePolicyEngine().decide(context)
    assert decision.runtime_action is expected


def test_retry_requires_retryable_and_attempt_budget():
    context = FailureContext(
        kind=FailureKind.MODEL_PROVIDER_ERROR,
        origin=FailureOrigin.PROVIDER,
        phase=FailurePhase.PROVIDER_CALL,
        message="timeout",
        retryable=True,
        fallback_safe=True,
    )
    policy = FailurePolicyEngine()
    assert policy.decide(context, attempts_remaining=True).retry_same_route is True
    assert policy.decide(context, attempts_remaining=False).retry_same_route is False


def test_fallback_requires_explicit_fallback_safe():
    policy = FailurePolicyEngine()
    unsafe = FailureContext(
        kind=FailureKind.MODEL_PROTOCOL_ERROR,
        origin=FailureOrigin.MODEL,
        phase=FailurePhase.PROTOCOL_VALIDATE,
        message="boundary violation",
        retryable=False,
        fallback_safe=False,
    )
    safe = FailureContext(
        kind=FailureKind.MODEL_PROVIDER_ERROR,
        origin=FailureOrigin.PROVIDER,
        phase=FailurePhase.PROVIDER_CALL,
        message="provider unavailable",
        retryable=False,
        fallback_safe=True,
    )
    assert policy.decide(unsafe, fallback_available=True).fallback_allowed is False
    assert policy.decide(safe, fallback_available=True).fallback_allowed is True


def test_diagnostic_call_id_does_not_change_repeat_identity():
    from harness.core.failures import Failure

    first = FailureContext(
        kind=FailureKind.MODEL_PROVIDER_ERROR,
        origin=FailureOrigin.PROVIDER,
        phase=FailurePhase.PROVIDER_CALL,
        message="same timeout",
        route_alias="m",
        provider_id="p",
        model_id="x",
        call_id="call-1",
    )
    second = FailureContext(
        kind=FailureKind.MODEL_PROVIDER_ERROR,
        origin=FailureOrigin.PROVIDER,
        phase=FailurePhase.PROVIDER_CALL,
        message="same timeout",
        route_alias="m",
        provider_id="p",
        model_id="x",
        call_id="call-2",
    )
    assert Failure(first.kind, first.message, context=first).signature == Failure(
        second.kind, second.message, context=second
    ).signature
