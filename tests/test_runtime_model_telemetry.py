from harness.core.runtime_model_telemetry import RuntimeModelTelemetryMixin


class FakeGateway:
    def telemetry_snapshot(self):
        return {
            "requests": 2,
            "failures": 1,
            "protocol_repairs": 1,
            "last_provider_call_id": "model-call-000002",
            "last_failure_context": {
                "schema_version": "failure-context-v1",
                "kind": "model_provider_error",
                "origin": "provider",
                "phase": "provider_call",
                "call_id": "model-call-000002",
                "stderr_digest": "a" * 64,
            },
        }


class FakeController:
    def __init__(self):
        self.model_attempt_sequence = 0
        self.last_context_compile = None
        self.last_protocol_decode = None
        self.model = FakeGateway()


class BaseRuntime:
    def step_once(self):
        self.controller.model_attempt_sequence += 1
        self.controller.last_context_compile = {
            "schema_version": "context-compile-telemetry-v1",
            "compiled_estimated_input_tokens": 100,
            "source_estimated_input_tokens": 200,
        }
        self.controller.last_protocol_decode = {
            "kind": "tool",
            "lexical_repaired": True,
            "lexical_repair_kind": "raw_control_character",
        }
        return False


class Runtime(RuntimeModelTelemetryMixin, BaseRuntime):
    def __init__(self, *, prior_attempts=0):
        self.controller = FakeController()
        self.metrics = {
            "model_attempts": prior_attempts,
            "model_protocol_lexical_repairs": 0,
        }
        self.rows = []

    def log(self, kind, payload):
        self.rows.append((kind, payload))
        return payload


def test_model_attempt_emits_context_protocol_and_gateway_diagnostics():
    runtime = Runtime()

    assert runtime.step_once() is False

    assert runtime.metrics["model_attempts"] == 1
    assert runtime.metrics["model_protocol_lexical_repairs"] == 1
    kinds = [kind for kind, _ in runtime.rows]
    assert kinds == [
        "model.context_compile",
        "model.protocol_decode",
        "model.gateway_telemetry",
    ]
    assert all(payload["authority"] == "diagnostic_only" for _, payload in runtime.rows)
    assert all(payload["attempt"] == 1 for _, payload in runtime.rows)
    gateway = runtime.rows[-1][1]["telemetry"]
    assert gateway["last_provider_call_id"] == "model-call-000002"
    assert gateway["last_failure_context"]["phase"] == "provider_call"
    assert len(gateway["last_failure_context"]["stderr_digest"]) == 64


def test_resume_restored_metric_owns_durable_attempt_number():
    runtime = Runtime(prior_attempts=7)
    assert runtime.controller.model_attempt_sequence == 0

    assert runtime.step_once() is False

    assert runtime.controller.model_attempt_sequence == 1
    assert runtime.metrics["model_attempts"] == 8
    assert all(payload["attempt"] == 8 for _, payload in runtime.rows)


def test_recovery_only_step_does_not_duplicate_model_telemetry():
    runtime = Runtime()
    runtime.controller.model_attempt_sequence = 3

    class RecoveryOnly:
        def step_once(self):
            return True

    class RecoveryRuntime(RuntimeModelTelemetryMixin, RecoveryOnly):
        def __init__(self):
            self.controller = runtime.controller
            self.metrics = runtime.metrics
            self.rows = []

        def log(self, kind, payload):
            self.rows.append((kind, payload))

    recovery = RecoveryRuntime()
    assert recovery.step_once() is True
    assert recovery.rows == []
