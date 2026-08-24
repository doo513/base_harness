import json

from harness.config import ModelConfig, SecretResolver
from harness.model_gateway import (
    LMStudioProvider,
    ModelGateway,
    ModelRequest,
    ModelResponse,
    OllamaProvider,
    ProviderCapabilities,
    ProviderRegistry,
)


class FakeLocalProvider:
    provider_id = "fake-local"
    capabilities = ProviderCapabilities(structured_output=True)
    protocol_enforced = True

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            content=self.outputs.pop(0),
            provider_id=self.provider_id,
            model_id="local-test",
        )


def _gateway(provider):
    registry = ProviderRegistry()
    registry.register("fake-local", lambda config, resolver: provider)
    return ModelGateway(
        models={"local": ModelConfig(provider="fake-local", model="local-test")},
        default_model="local",
        registry=registry,
        max_attempts_per_model=2,
        retry_backoff_seconds=0,
    )


def test_gateway_repairs_truncated_json_before_controller_sees_it():
    provider = FakeLocalProvider([
        '{"kind":"plan","payload":{"objective":"inspect","tasks":[',
        '{"kind":"tool","payload":{"tool":"directory.list","args":{}}}',
    ])
    gateway = _gateway(provider)

    raw = gateway.complete(system="system", user="user")

    assert json.loads(raw)["kind"] == "tool"
    assert len(provider.requests) == 2
    assert "MODEL PROTOCOL REPAIR" in provider.requests[1].user
    telemetry = gateway.telemetry_snapshot()
    assert telemetry["protocol_repairs"] == 1
    assert telemetry["failures"] == 1
    assert telemetry["last_error_kind"] is None


def test_gateway_repairs_schema_invalid_empty_tool_name():
    provider = FakeLocalProvider([
        '{"kind":"tool","payload":{"tool":"","args":{}}}',
        '{"kind":"tool","payload":{"tool":"file.read","args":{"path":"pyproject.toml"}}}',
    ])
    gateway = _gateway(provider)

    decision = json.loads(gateway.complete(system="system", user="user"))

    assert decision["payload"]["tool"] == "file.read"
    assert gateway.telemetry_snapshot()["protocol_repairs"] == 1


def test_gateway_accepts_fenced_json_but_returns_canonical_json():
    provider = FakeLocalProvider([
        '```json\n{"kind":"complete","payload":{"reason":"done"}}\n```',
    ])
    gateway = _gateway(provider)

    raw = gateway.complete(system="system", user="user")

    assert raw.startswith("{") and "```" not in raw
    assert json.loads(raw) == {"kind": "complete", "payload": {"reason": "done"}}


def test_default_registry_exposes_explicit_local_providers():
    providers = ProviderRegistry.default().providers()
    assert "ollama" in providers
    assert "lm-studio" in providers


def test_local_provider_default_endpoints_and_protocol_capability():
    resolver = SecretResolver({})
    ollama = OllamaProvider(ModelConfig(provider="ollama", model="gemma"), secret_resolver=resolver)
    lmstudio = LMStudioProvider(ModelConfig(provider="lm-studio", model="local"), secret_resolver=resolver)

    assert ollama.endpoint == "http://127.0.0.1:11434/api/chat"
    assert lmstudio.endpoint == "http://127.0.0.1:1234/v1/chat/completions"
    # Providers may enforce schema natively, but Gateway still applies the same
    # canonical response/protocol normalization to every route.
    assert ollama.protocol_enforced is True
    assert lmstudio.protocol_enforced is True
