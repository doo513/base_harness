import sys

import pytest

from harness.config import ConfigError, ModelConfig
from harness.config_contracts import validate_model_config_contract
from harness.model_capabilities import inspect_model_capabilities
from harness.model_gateway import ModelGateway


def test_builtin_provider_rejects_unknown_option_fail_closed():
    with pytest.raises(ConfigError, match="unsupported options"):
        ModelGateway(
            models={
                "local": ModelConfig(
                    provider="ollama",
                    model="m",
                    options={"imaginary_future_flag": True},
                )
            },
            default_model="local",
        )


def test_capability_output_override_keys_are_validated_not_silently_ignored():
    valid = ModelConfig(
        provider="command",
        command=f'"{sys.executable}" -c "print(1)"',
        options={
            "output_contract": "json",
            "output_enforcement": "posthoc_validated",
        },
    )
    validate_model_config_contract(valid)

    with pytest.raises(ConfigError, match="output_contract"):
        validate_model_config_contract(
            ModelConfig(
                provider="command",
                command=f'"{sys.executable}" -c "print(1)"',
                options={"output_contract": "magic"},
            )
        )


def test_command_route_declares_text_unless_adapter_contract_strengthens_it():
    generic = ModelGateway(
        models={
            "cmd": ModelConfig(
                provider="command",
                command=f'"{sys.executable}" -c "print(1)"',
            )
        },
        default_model="cmd",
    )
    snapshot = inspect_model_capabilities(generic)
    assert snapshot["routes"]["cmd"]["features"]["structured_output"] is False
    assert snapshot["routes"]["cmd"]["output"]["contract"] == "text"


def test_model_gateway_preflight_rejects_missing_command_executable():
    gateway = ModelGateway(
        models={
            "cmd": ModelConfig(
                provider="command",
                command="definitely-not-a-real-harness-executable --version",
            )
        },
        default_model="cmd",
    )
    with pytest.raises(ConfigError, match="executable"):
        gateway.preflight()


def test_model_gateway_preflight_reports_active_route_without_calling_model():
    gateway = ModelGateway(
        models={
            "cmd": ModelConfig(
                provider="command",
                command=f'"{sys.executable}" -c "print(1)"',
            )
        },
        default_model="cmd",
    )
    report = gateway.preflight()
    assert report["schema_version"] == "model-preflight-v1"
    assert report["routes"][0]["status"] == "ready"
