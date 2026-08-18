import json
import shlex
import sys

from harness.config import ModelConfig, SecretResolver
from harness.model_gateway import (
    ModelGateway,
    ModelRequest,
    ModelResponse,
    ModelUsage,
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

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_model_gateway_retries_retryable_error_then_succeeds():
    provider = FakeProvider("fake", [
        ProviderError("temporary", kind="rate_limit", retryable=True),
        ModelResponse(
            content='{"kind":"complete","payload":{"reason":"ok"}}',
            provider_id="fake",
            model_id="m",
            request_id="req-1",
            usage=ModelUsage(input_tokens=10, output_tokens=4, total_tokens=14),
            latency_seconds=0.1,
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
    raw = gateway.complete(system="s", user="u")
    assert json.loads(raw)["kind"] == "complete"
    telemetry = gateway.telemetry_snapshot()
    assert telemetry["requests"] == 2
    assert telemetry["failures"] == 1
    assert telemetry["total_tokens"] == 14
    assert telemetry["last_request_id"] == "req-1"


def test_model_gateway_falls_back_without_granting_any_kernel_authority():
    primary = FakeProvider("primary-provider", [ProviderError("down", kind="network_error", retryable=False)])
    fallback = FakeProvider("fallback-provider", [ModelResponse(content="{}", provider_id="fallback-provider", model_id="b")])
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
    assert gateway.complete(system="s", user="u") == "{}"
    telemetry = gateway.telemetry_snapshot()
    assert telemetry["fallbacks"] == 1
    assert telemetry["last_provider"] == "fallback-provider"


def test_model_gateway_descriptor_keeps_secret_reference_not_secret_value():
    registry = ProviderRegistry()
    provider = FakeProvider("fake", [ModelResponse(content="{}", provider_id="fake", model_id="m")])
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


def test_single_command_gateway_uses_argv_execution_and_controller_wire_format():
    program = (
        "import json,sys; "
        "obj=json.load(sys.stdin); "
        "assert 'system' in obj and 'user' in obj; "
        "print(json.dumps({'kind':'complete','payload':{'reason':'ok'}}))"
    )
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(program)}"
    gateway = ModelGateway.single_command(command)
    raw = gateway.complete(system="system", user="user")
    assert json.loads(raw) == {"kind": "complete", "payload": {"reason": "ok"}}
