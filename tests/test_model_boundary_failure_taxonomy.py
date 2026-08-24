import pytest

from harness.core.controller import ControllerBoundaryError, LLMController
from harness.core.failures import Failure, FailureKind, FailureRouter, RecoveryAction
from harness.model_error_envelope import encode_model_error, extract_embedded_model_error


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


def test_protocol_provider_error_becomes_model_protocol_boundary_error():
    controller = LLMController(RaisingModel(ProviderFailure("protocol_invalid_json", True)))
    with pytest.raises(ControllerBoundaryError) as caught:
        controller._complete(system="s", user="u")
    assert caught.value.failure_kind is FailureKind.MODEL_PROTOCOL_ERROR
    assert caught.value.retry_safe is True
    assert caught.value.signature_key == "model-protocol:protocol_invalid_json"


def test_transport_provider_error_remains_model_provider_error():
    controller = LLMController(RaisingModel(ProviderFailure("timeout", True)))
    with pytest.raises(ControllerBoundaryError) as caught:
        controller._complete(system="s", user="u")
    assert caught.value.failure_kind is FailureKind.MODEL_PROVIDER_ERROR
    assert caught.value.retry_safe is True
    assert caught.value.signature_key == "model-provider:timeout"


def test_embedded_command_adapter_protocol_error_overrides_outer_execution_error():
    marker = encode_model_error(
        kind="protocol_schema",
        message="tool.tool must be non-empty",
        retryable=True,
    )
    outer = ProviderFailure("execution_error", False)
    outer.args = (f"model command failed (2): prefix\n{marker}\n",)

    controller = LLMController(RaisingModel(outer))
    with pytest.raises(ControllerBoundaryError) as caught:
        controller._complete(system="s", user="u")

    assert caught.value.failure_kind is FailureKind.MODEL_PROTOCOL_ERROR
    assert caught.value.retry_safe is True
    assert caught.value.signature_key == "model-protocol:protocol_schema"


def test_embedded_error_parser_ignores_unmarked_stderr():
    assert extract_embedded_model_error("random stderr {not json}") is None


def test_model_protocol_routes_to_targeted_repair():
    router = FailureRouter()
    failure = Failure(FailureKind.MODEL_PROTOCOL_ERROR, "bad JSON")
    assert router.route(failure) is RecoveryAction.REPAIR


def test_actor_workflow_routes_to_replan_not_protocol_repair():
    router = FailureRouter()
    failure = Failure(FailureKind.ACTOR_WORKFLOW_ERROR, "cycle in task graph")
    assert router.route(failure) is RecoveryAction.REPLAN


def test_provider_retry_requires_explicit_retry_safe():
    router = FailureRouter()
    unsafe = Failure(FailureKind.MODEL_PROVIDER_ERROR, "provider unavailable")
    safe = Failure(
        FailureKind.MODEL_PROVIDER_ERROR,
        "provider timed out",
        retry_safe=True,
    )
    assert router.route(unsafe) is RecoveryAction.OBSERVE
    assert router.route(safe) is RecoveryAction.RETRY
