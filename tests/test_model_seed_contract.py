from harness.config import ModelConfig, SecretResolver
from harness.model_gateway import (
    LMStudioProvider,
    ModelRequest,
    OllamaProvider,
    OpenAICompatibleProvider,
)


def test_openai_compatible_applies_configured_seed(monkeypatch):
    captured = {}

    def fake_http(endpoint, *, body, timeout_seconds, api_key=None):
        captured.update(body)
        return {
            "id": "r",
            "choices": [{"message": {"content": '{"kind":"complete","payload":{"reason":"ok"}}'}}],
        }, None

    monkeypatch.setattr("harness.model_gateway._http_json", fake_http)
    provider = OpenAICompatibleProvider(
        ModelConfig(
            provider="openai-compatible",
            model="m",
            endpoint="https://example.invalid/v1",
            options={"seed": 17},
        ),
        secret_resolver=SecretResolver({}),
    )
    provider.complete(ModelRequest(system="s", user="u"))
    assert captured["seed"] == 17


def test_ollama_applies_configured_seed(monkeypatch):
    captured = {}

    def fake_http(endpoint, *, body, timeout_seconds, api_key=None):
        captured.update(body)
        return {
            "message": {"content": '{"kind":"complete","payload":{"reason":"ok"}}'},
            "prompt_eval_count": 1,
            "eval_count": 1,
        }, None

    monkeypatch.setattr("harness.model_gateway._http_json", fake_http)
    provider = OllamaProvider(
        ModelConfig(provider="ollama", model="m", options={"seed": 19}),
        secret_resolver=SecretResolver({}),
    )
    provider.complete(ModelRequest(system="s", user="u"))
    assert captured["options"]["seed"] == 19


def test_lmstudio_applies_configured_seed(monkeypatch):
    captured = {}

    def fake_http(endpoint, *, body, timeout_seconds, api_key=None):
        captured.update(body)
        return {
            "choices": [{"message": {"content": '{"kind":"complete","payload":{"reason":"ok"}}'}}],
        }, None

    monkeypatch.setattr("harness.model_gateway._http_json", fake_http)
    provider = LMStudioProvider(
        ModelConfig(provider="lm-studio", model="m", options={"seed": 23}),
        secret_resolver=SecretResolver({}),
    )
    provider.complete(ModelRequest(system="s", user="u"))
    assert captured["seed"] == 23
