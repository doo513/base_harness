import pytest

from harness.core.controller import ControllerBoundaryError, LLMController
from harness.core.failures import (
    Failure,
    FailureContext,
    FailureKind,
    FailureOrigin,
    FailurePhase,
    FailurePolicyEngine,
    FailureRouter,
    RecoveryAction,
)
from harness.model_error_envelope import encode_model_error, extract_embedded_model_error
from harness.model_gateway import ModelGatewayFailure


class ProviderFailure(RuntimeError):
    def __init__(self, kind, retryable):
        super().__init__(f"provider failed: {kind}")
        self.kind = kind
        self.retryable = retryable


class RaisingModel:
    def __init__(self, exc):
        self.exc = exc

    def complete(self, *, system, user):
        raise self.exc


def test_unclassified_adapter_exception_is_harness_integration_failure_not_provider_guess():
    controller = LLMController(RaisingModel(ProviderFailure("timeout", True)))
    with pytest.raises(ControllerBoundaryError) as caught:
        controller._complete(system="s", user="u")
    assert caught.value.failure_context.kind is FailureKind.IMPLEMENTATION_ERROR
    assert caught.value.failure_context.origin is FailureOrigin.HARNESS
    assert caught.value.failure_context.phase is FailurePhase.CONTROLLER
    assert caught.value.retry_safe is False


def test_gateway_failure_context_passes_through_controller_without_reclassification():
    context = FailureContext(
        kind=FailureKind.MODEL_PROVIDER_ERROR,
        origin=FailureOrigin.PROVIDER,
        phase=FailurePhase.PROVIDER_CALL,
        message="provider timed out",
        retryable=True,
        fallback_safe=True,
        route_alias="primary",
        provider_id="fake",
        model_id="m",
        call_id="model-call-000001",
    )
    policy = FailurePolicyEngine().decide(context)
    controller = LLMController(RaisingModel(ModelGatewayFailure(context, policy)))
    with pytest.raises(ControllerBoundaryError) as caught:
        controller._complete(system="s", user="u")
    assert caught.value.failure_context == context
    assert caught.value.failure_kind is FailureKind.MODEL_PROVIDER_ERROR


def test_embedded_error_parser_ignores_unmarked_stderr_and_accepts_explicit_marker():
    assert extract_embedded_model_error("random stderr {not json}") is None
    marker = encode_model_error(
        kind="protocol_schema",
        message="tool.tool must be non-empty",
        retryable=True,
    )
    parsed = extract_embedded_model_error("prefix\n" + marker + "\n")
    assert parsed is not None
    assert parsed.kind == "protocol_schema"
    assert parsed.retryable is True


def test_model_protocol_routes_to_targeted_runtime_repair_after_gateway_exhaustion():
    router = FailureRouter()
    failure = Failure(FailureKind.MODEL_PROTOCOL_ERROR, "bad JSON")
    assert router.route(failure) is RecoveryAction.REPAIR


def test_actor_workflow_routes_to_replan_not_protocol_repair():
    router = FailureRouter()
    failure = Failure(FailureKind.ACTOR_WORKFLOW_ERROR, "cycle in task graph")
    assert router.route(failure) is RecoveryAction.REPLAN


def test_provider_retry_and_fallback_are_gateway_policy_not_runtime_retry():
    policy = FailurePolicyEngine()
    context = FailureContext(
        kind=FailureKind.MODEL_PROVIDER_ERROR,
        origin=FailureOrigin.PROVIDER,
        phase=FailurePhase.PROVIDER_CALL,
        message="provider timed out",
        retryable=True,
        fallback_safe=True,
    )
    retry = policy.decide(context, attempts_remaining=True, fallback_available=True)
    assert retry.retry_same_route is True
    assert retry.fallback_allowed is False

    fallback = policy.decide(context, attempts_remaining=False, fallback_available=True)
    assert fallback.retry_same_route is False
    assert fallback.fallback_allowed is True

    runtime = FailureRouter().route(
        Failure(FailureKind.MODEL_PROVIDER_ERROR, "provider timed out", retry_safe=True)
    )
    assert runtime is RecoveryAction.OBSERVE
