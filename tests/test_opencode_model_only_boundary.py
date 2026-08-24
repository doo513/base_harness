import json
from types import SimpleNamespace

from harness.opencode_adapter import (
    DEFAULT_OPENCODE_AGENT,
    _deny_external_tools_inline_config,
    run_opencode_decision,
)


def test_inline_config_denies_external_tools_but_allows_internal_structured_output():
    config = json.loads(_deny_external_tools_inline_config())

    assert config["permission"]["*"] == "deny"
    assert config["permission"]["StructuredOutput"] == "allow"
    agent = config["agent"][DEFAULT_OPENCODE_AGENT]
    assert agent["mode"] == "primary"
    assert agent["permission"]["*"] == "deny"
    assert agent["permission"]["StructuredOutput"] == "allow"
    assert "model transport" in agent["prompt"]


def test_default_opencode_run_uses_harness_model_agent(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        inline = json.loads(kwargs["env"]["OPENCODE_CONFIG_CONTENT"])
        assert DEFAULT_OPENCODE_AGENT in inline["agent"]
        return SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=json.dumps({
                "type": "text",
                "sessionID": "s",
                "part": {
                    "type": "text",
                    "text": '{"kind":"complete","payload":{"reason":"ok"}}',
                },
            }),
        )

    monkeypatch.setattr("harness.opencode_adapter.subprocess.run", fake_run)
    result = run_opencode_decision(
        system="system",
        user="user",
        binary="opencode",
        model="opencode/free-model",
        timeout_seconds=10,
    )

    assert json.loads(result.decision_json)["kind"] == "complete"
    assert result.external_tool_uses == 0
    argv = captured["argv"]
    assert argv[argv.index("--agent") + 1] == DEFAULT_OPENCODE_AGENT
    assert argv[argv.index("--model") + 1] == "opencode/free-model"
