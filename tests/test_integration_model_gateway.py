import json
import shlex
import sys

import pytest

from harness.config import ModelConfig, SecretResolver
from harness.core.failures import FailureKind
from harness.model_gateway import (
    CommandProvider,
    ModelGateway,
    ModelGatewayFailure,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    NormalizedModelResponse,
    ProviderCapabilities,
    ProviderError,
    ProviderRegistry,
)


class FakeProvider:
    capabilities = ProviderCapabilities(structured_output=True)

    def __init__(self, provider_id, outcomes):
        self.provider_id = provider_id
        self.outcomes = list(outcomes)
        self.calls = 0
        self.requests = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _valid(provider_id="fake", model_id="m", reason="ok"):
    return ModelResponse(
        content=json.dumps({"kind": "complete", "payload": {"reason": reason}}),
        provider_id=provider_id,
        model_id=model_id,
        request_id="req-1",
        usage=ModelUsage(input_tokens=10, output_tokens=4, total_tokens=14),
        latency_seconds=0.1,
    )


def _python_command(program: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(program)}"


def test_model_gateway_retries_retryable_error_then_succeeds():
    provider = FakeProvider("fake", [
        ProviderError("temporary", kind="rate_limit", retryable=True),
        _valid(),
    ])
    registry = ProviderRegistry()
    registry.register("fake", lambda config, resolver: provider)
    gateway = ModelGateway(
        models={"primary": ModelConfig(provider="fake", model="m")},
        default_model="primary",
        registry=registry,
        max_attempts_per_model=2,
        retry_backoff_seconds=0,
    )
    raw = gateway.complete(system="s", user="u")
    assert json.loads(raw)["kind"] == "complete"
    telemetry = gateway.telemetry_snapshot()
    assert telemetry["requests"] == 2
    assert telemetry["failures"] == 1
    assert telemetry["total_tokens"] == 14
    assert telemetry["last_request_id"] == "req-1"
    assert telemetry["last_response"]["schema_version"] == "normalized-model-response-v1"


def test_model_gateway_falls_back_only_after_common_policy_allows_it():
    primary = FakeProvider(
        "primary-provider",
        [ProviderError("down", kind="network_error", retryable=False)],
    )
    fallback = FakeProvider("fallback-provider", [_valid("fallback-provider", "b", "fallback")])
    registry = ProviderRegistry()
    registry.register("a", lambda config, resolver: primary)
    registry.register("b", lambda config, resolver: fallback)
    gateway = ModelGateway(
        models={
            "primary": ModelConfig(provider="a", model="a-model"),
            "fallback": ModelConfig(provider="b", model="b-model"),
        },
        default_model="primary",
        fallback_models=("fallback",),
        registry=registry,
        max_attempts_per_model=1,
    )
    assert json.loads(gateway.complete(system="s", user="u"))["payload"]["reason"] == "fallback"
    telemetry = gateway.telemetry_snapshot()
    assert telemetry["fallbacks"] == 1
    assert telemetry["last_provider"] == "fallback-provider"


def test_protocol_normalization_and_repair_are_gateway_wide_not_provider_specific():
    provider = FakeProvider("fake", [
        ModelResponse(
            content='{"kind":"tool","payload":{"tool":"","args":{}}}',
            provider_id="fake",
            model_id="m",
        ),
        ModelResponse(
            content='```json\n{"kind":"complete","payload":{"reason":"fixed"}}\n```',
            provider_id="fake",
            model_id="m",
        ),
    ])
    registry = ProviderRegistry()
    registry.register("fake", lambda config, resolver: provider)
    gateway = ModelGateway(
        models={"primary": ModelConfig(provider="fake", model="m")},
        default_model="primary",
        registry=registry,
        max_attempts_per_model=2,
        retry_backoff_seconds=0,
    )

    result = gateway.complete_response(system="s", user="u")

    assert isinstance(result, NormalizedModelResponse)
    assert json.loads(result.content)["payload"]["reason"] == "fixed"
    assert "MODEL PROTOCOL REPAIR" in provider.requests[1].user
    telemetry = gateway.telemetry_snapshot()
    assert telemetry["protocol_repairs"] == 1
    assert telemetry["last_provider_call_id"].startswith("model-call-")


def test_gateway_exhaustion_exposes_failure_context_not_exception_class_policy():
    provider = FakeProvider(
        "fake",
        [ProviderError("bad", kind="invalid_response", retryable=False)],
    )
    registry = ProviderRegistry()
    registry.register("fake", lambda config, resolver: provider)
    gateway = ModelGateway(
        models={"primary": ModelConfig(provider="fake", model="m")},
        default_model="primary",
        registry=registry,
        max_attempts_per_model=1,
    )

    with pytest.raises(ModelGatewayFailure) as caught:
        gateway.complete(system="s", user="u")

    context = caught.value.failure_context
    assert context.kind is FailureKind.MODEL_PROVIDER_ERROR
    assert context.route_alias == "primary"
    assert context.provider_id == "fake"
    assert context.call_id.startswith("model-call-")


def test_model_gateway_descriptor_keeps_secret_reference_not_secret_value():
    registry = ProviderRegistry()
    provider = FakeProvider("fake", [_valid()])
    registry.register("fake", lambda config, resolver: provider)
    config = ModelConfig(provider="fake", model="m", api_key=None)
    gateway = ModelGateway(
        models={"primary": config},
        default_model="primary",
        registry=registry,
        secret_resolver=SecretResolver({"KEY": "super-secret"}),
    )
    descriptor = gateway.descriptor()
    assert "super-secret" not in repr(descriptor)
    assert descriptor["normalized_response_schema"] == "normalized-model-response-v1"
    assert descriptor["retry_policy"]["routing_input"] == "FailureContext-not-exception-type"


def test_single_command_gateway_uses_argv_execution_and_controller_wire_format():
    program = (
        "import json,sys; "
        "obj=json.load(sys.stdin); "
        "assert 'system' in obj and 'user' in obj; "
        "print(json.dumps({'kind':'complete','payload':{'reason':'ok'}}))"
    )
    gateway = ModelGateway.single_command(_python_command(program))
    raw = gateway.complete(system="system", user="user")
    assert json.loads(raw) == {"kind": "complete", "payload": {"reason": "ok"}}


def test_command_provider_minimizes_parent_environment_by_default(monkeypatch):
    monkeypatch.setenv("HARNESS_SHOULD_NOT_LEAK", "secret")
    provider = CommandProvider(
        ModelConfig(
            provider="command",
            command=_python_command('print("{}")'),
        )
    )
    env = provider._environment()
    assert env is not None
    assert "HARNESS_SHOULD_NOT_LEAK" not in env


def test_command_provider_explicit_environment_allowlist_is_narrow(monkeypatch):
    monkeypatch.setenv("HARNESS_ALLOWED", "value")
    provider = CommandProvider(
        ModelConfig(
            provider="command",
            command=_python_command('print("{}")'),
            options={"command_env_allowlist": ["HARNESS_ALLOWED"]},
        )
    )
    env = provider._environment()
    assert env is not None
    assert env["HARNESS_ALLOWED"] == "value"
