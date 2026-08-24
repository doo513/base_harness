from harness.model_capabilities import inspect_model_capabilities


class FakeGateway:
    def descriptor(self):
        return {
            "schema_version": "model-gateway-v2",
            "default_model": "local",
            "models": {
                "local": {
                    "provider": "command",
                    "model": None,
                    "endpoint": None,
                    "timeout_seconds": 180,
                    "options": {
                        "adapter": "opencode",
                        "context_window": 32768,
                        "reserved_output_tokens": 2048,
                    },
                },
                "ollama": {
                    "provider": "ollama",
                    "model": "gemma3:latest",
                    "endpoint": "http://127.0.0.1:11434",
                    "timeout_seconds": 120,
                    "options": {
                        "context_window": 8192,
                        "max_tokens": 1024,
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


def test_capability_snapshot_describes_features_constraints_not_intelligence_tiers():
    snapshot = inspect_model_capabilities(FakeGateway())

    assert snapshot["policy"]["model_tiering"] == "disabled"
    assert snapshot["policy"]["intelligence_classification"] == "none"
    assert set(snapshot["routes"]) == {"local", "ollama", "remote"}

    opencode = snapshot["routes"]["local"]
    assert opencode["adapter"] == "opencode"
    assert opencode["execution_location"] == "local_process"
    assert opencode["features"]["structured_output"] is True
    assert opencode["features"]["native_tool_calling"] is False
    assert opencode["constraints"]["context_window"] == 32768
    assert opencode["constraints"]["tool_execution_boundary"] == "harness_only"
    assert opencode["model_tier"] is None
    assert opencode["model_size_class"] is None

    ollama = snapshot["routes"]["ollama"]
    assert ollama["features"]["reasoning"] is True
    assert ollama["constraints"]["reserved_output_tokens"] == 1024

    remote = snapshot["routes"]["remote"]
    assert remote["execution_location"] == "remote_endpoint"
    assert remote["features"]["reasoning"] is True
    assert "config_override" in remote["feature_source"]


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
