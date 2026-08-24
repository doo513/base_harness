from harness.model_capabilities import inspect_model_capabilities


class FakeGateway:
    def descriptor(self):
        return {
            "schema_version": "model-gateway-v2",
            "default_model": "local",
            "models": {
                "local": {
                    "provider": "command",
                    "model": "opencode/free-model",
                    "endpoint": None,
                    "timeout_seconds": 180,
                    "options": {
                        "adapter": "opencode",
                        "context_window": 32768,
                        "reserved_output_tokens": 2048,
                        "context_safety_margin_tokens": 1024,
                    },
                },
                "command": {
                    "provider": "command",
                    "model": None,
                    "endpoint": None,
                    "timeout_seconds": 30,
                    "options": {},
                },
                "ollama": {
                    "provider": "ollama",
                    "model": "gemma3:latest",
                    "endpoint": "http://127.0.0.1:11434",
                    "timeout_seconds": 120,
                    "options": {
                        "context_window": 8192,
                        "max_tokens": 1024,
                        "context_safety_margin_tokens": 256,
                    },
                },
                "remote": {
                    "provider": "openai-compatible",
                    "model": "remote-model",
                    "endpoint": "https://example.invalid/v1",
                    "timeout_seconds": 120,
                    "options": {
                        "capability_reasoning": True,
                    },
                },
                "remote-json": {
                    "provider": "openai-compatible",
                    "model": "remote-model",
                    "endpoint": "https://example.invalid/v1",
                    "timeout_seconds": 120,
                    "options": {
                        "json_mode": True,
                    },
                },
            },
        }

    def telemetry_snapshot(self):
        return {
            "requests": 10,
            "failures": 2,
            "protocol_repairs": 1,
            "last_provider": "command",
            "last_model": None,
            "last_error_kind": None,
        }


def test_capability_snapshot_describes_route_contracts_not_intelligence_tiers():
    snapshot = inspect_model_capabilities(FakeGateway())

    assert snapshot["policy"]["model_tiering"] == "disabled"
    assert snapshot["policy"]["intelligence_classification"] == "none"
    assert set(snapshot["routes"]) == {"command", "local", "ollama", "remote", "remote-json"}

    opencode = snapshot["routes"]["local"]
    assert opencode["adapter"] == "opencode"
    assert opencode["execution_location"] == "local_process"
    assert opencode["wrapper_layers"] == ["opencode"]
    assert opencode["features"]["structured_output"] is True
    assert opencode["features"]["native_tool_calling"] is False
    assert opencode["input"]["context_window"] == 32768
    assert opencode["input"]["effective_input_budget"] == 29696
    assert opencode["output"]["contract"] == "json"
    assert opencode["output"]["enforcement"] == "posthoc_validated"
    assert opencode["output"]["semantic_repair"] == "forbidden"
    assert opencode["constraints"]["tool_execution_boundary"] == "harness_only"
    assert opencode["model_tier"] is None
    assert opencode["model_size_class"] is None

    command = snapshot["routes"]["command"]
    assert command["features"]["structured_output"] is False
    assert command["output"]["contract"] == "text"
    assert command["output"]["enforcement"] == "prompt_only"

    ollama = snapshot["routes"]["ollama"]
    assert ollama["features"]["reasoning"] is True
    assert ollama["input"]["reserved_output_tokens"] == 1024
    assert ollama["input"]["effective_input_budget"] == 6912
    assert ollama["output"] == {
        "contract": "json_schema",
        "enforcement": "provider_native",
        "canonical_protocol": "harness-json-decision",
        "bounded_lexical_repair": ["raw_control_character"],
        "semantic_repair": "forbidden",
    }

    remote = snapshot["routes"]["remote"]
    assert remote["execution_location"] == "remote_endpoint"
    assert remote["features"]["reasoning"] is True
    assert remote["features"]["structured_output"] is False
    assert remote["output"]["contract"] == "text"
    assert "config_override" in remote["feature_source"]

    remote_json = snapshot["routes"]["remote-json"]
    assert remote_json["features"]["structured_output"] is True
    assert remote_json["output"]["contract"] == "json"
    assert remote_json["output"]["enforcement"] == "provider_native"


def test_capability_snapshot_reports_observed_failure_rates_without_reclassifying_model():
    snapshot = inspect_model_capabilities(FakeGateway())
    observed = snapshot["observed"]

    assert observed["scope"] == "gateway_session_aggregate"
    assert observed["requests"] == 10
    assert observed["failures"] == 2
    assert observed["protocol_repairs"] == 1
    assert observed["failure_rate"] == 0.2
    assert observed["protocol_repair_rate"] == 0.1
    assert "tier" not in observed


def test_output_contract_can_be_explicitly_overridden_without_model_tiering():
    class Gateway:
        def descriptor(self):
            return {
                "default_model": "wrapped",
                "models": {
                    "wrapped": {
                        "provider": "command",
                        "model": "x",
                        "endpoint": None,
                        "timeout_seconds": 5,
                        "options": {
                            "output_contract": "json_schema",
                            "output_enforcement": "wrapper_enforced",
                        },
                    }
                },
            }

    route = inspect_model_capabilities(Gateway())["routes"]["wrapped"]
    assert route["output"]["contract"] == "json_schema"
    assert route["output"]["enforcement"] == "wrapper_enforced"
    assert route["model_tier"] is None
