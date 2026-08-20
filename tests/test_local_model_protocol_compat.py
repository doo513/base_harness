import json
from types import SimpleNamespace
import urllib.request

import pytest

from harness.config import ModelConfig, SecretResolver
from harness.core.controller import LLMController, _extract_json_object
from harness.model_gateway import ModelRequest, OpenAICompatibleProvider, ProviderError


class _HTTPResponse:
    def __init__(self, payload):
        self.payload = payload
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class _SequenceModel:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def complete(self, *, system, user):
        self.calls += 1
        return self.outputs.pop(0)


def _ollama_provider():
    return OpenAICompatibleProvider(
        ModelConfig(
            provider="openai-compatible",
            model="gemma-test",
            endpoint="http://127.0.0.1:11434/v1/",
        ),
        secret_resolver=SecretResolver({}),
    )


def test_ollama_actor_request_uses_json_mode_and_disables_reasoning(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _HTTPResponse({
            "id": "req-1",
            "choices": [{
                "message": {"role": "assistant", "content": '{"kind":"complete","payload":{"reason":"ok"}}'},
                "finish_reason": "stop",
            }],
        })

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = _ollama_provider()
    response = provider.complete(ModelRequest(system="system", user="user"))

    assert response.content.startswith("{")
    assert captured["body"]["reasoning_effort"] == "none"
    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_ollama_reasoning_only_response_is_retryable_empty_response(monkeypatch):
    def fake_urlopen(request, timeout):
        return _HTTPResponse({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning": "internal reasoning that must not become the actor decision",
                },
                "finish_reason": "length",
            }],
        })

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = _ollama_provider()

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(ModelRequest(system="system", user="user"))

    assert exc_info.value.kind == "empty_response"
    assert exc_info.value.retryable is True
    assert "reasoning was present" in str(exc_info.value)


def test_controller_extracts_fenced_json_and_retries_one_empty_actor_response():
    fenced = "```json\n{\"kind\":\"complete\",\"payload\":{\"reason\":\"ok\"}}\n```"
    assert _extract_json_object(fenced)["kind"] == "complete"

    model = _SequenceModel(["", '{"kind":"complete","payload":{"reason":"ok"}}'])
    controller = LLMController(model)
    state = SimpleNamespace(agent_control=SimpleNamespace(tasks={}))

    decision = controller.decide("goal", state, {})
    assert decision.kind == "complete"
    assert model.calls == 2


def test_task_auto_promotion_only_applies_before_a_plan_exists():
    raw_task = '{"kind":"task","payload":{"id":"task-01","status":"active","note":"inspect"}}'

    empty_state = SimpleNamespace(agent_control=SimpleNamespace(tasks={}))
    promoted = LLMController(_SequenceModel([raw_task])).decide("goal", empty_state, {})
    assert promoted.kind == "plan"
    assert promoted.payload["tasks"][0]["id"] == "task-01"

    planned_state = SimpleNamespace(agent_control=SimpleNamespace(tasks={"known": object()}))
    preserved = LLMController(_SequenceModel([raw_task])).decide("goal", planned_state, {})
    assert preserved.kind == "task"
    assert preserved.payload["id"] == "task-01"
