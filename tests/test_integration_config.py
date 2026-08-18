import pytest

from harness.config import (
    ConfigError,
    SecretResolver,
    harness_config_from_mapping,
)


def test_config_parses_workspace_models_mcp_plugins_without_resolving_secrets():
    config = harness_config_from_mapping({
        "profile": "software",
        "run_dir": "./run",
        "workspace": {"root": ".", "cache_dir": ".cache/harness"},
        "default_model": "primary",
        "models": {
            "primary": {
                "provider": "openai-compatible",
                "model": "example-model",
                "endpoint": "https://example.invalid/v1",
                "api_key": "env:EXAMPLE_API_KEY",
            },
            "local": {
                "provider": "command",
                "command": "local-agent --json",
            },
        },
        "mcp": [{
            "name": "repo",
            "transport": "stdio",
            "command": ["mcp-repo"],
            "env": {"TOKEN": "env:MCP_TOKEN"},
        }],
        "plugins": [{"name": "example", "module": "example_plugin"}],
    })
    assert config.default_model == "primary"
    assert config.models["primary"].api_key.descriptor() == "env:EXAMPLE_API_KEY"
    assert config.mcp_servers[0].command == ("mcp-repo",)
    assert config.plugins[0].module == "example_plugin"
    descriptor = config.descriptor()
    assert descriptor["models"]["primary"]["api_key"] == "env:EXAMPLE_API_KEY"
    assert "secret-value" not in repr(descriptor)


def test_secret_resolver_fails_closed_when_environment_key_is_missing():
    resolver = SecretResolver({"PRESENT": "secret-value"})
    assert resolver.resolve("env:PRESENT") == "secret-value"
    with pytest.raises(ConfigError):
        resolver.resolve("env:MISSING")


def test_config_rejects_inline_secret_and_unknown_keys():
    with pytest.raises(ConfigError):
        harness_config_from_mapping({
            "models": {"primary": {"provider": "x", "model": "m", "api_key": "raw-secret"}},
            "default_model": "primary",
        })
    with pytest.raises(ConfigError):
        harness_config_from_mapping({"unexpected": True})


def test_config_rejects_missing_default_model_and_duplicate_extension_names():
    with pytest.raises(ConfigError):
        harness_config_from_mapping({"default_model": "missing"})
    with pytest.raises(ConfigError):
        harness_config_from_mapping({
            "mcp": [
                {"name": "dup", "transport": "stdio", "command": ["one"]},
                {"name": "dup", "transport": "stdio", "command": ["two"]},
            ]
        })
    with pytest.raises(ConfigError):
        harness_config_from_mapping({
            "plugins": [
                {"name": "dup", "module": "one"},
                {"name": "dup", "module": "two"},
            ]
        })
