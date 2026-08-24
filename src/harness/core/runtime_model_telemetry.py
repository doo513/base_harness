from __future__ import annotations

from typing import Any


class RuntimeModelTelemetryMixin:
    """Persist non-authoritative model-boundary diagnostics around step_once.

    This mixin observes Controller/Gateway telemetry only. It cannot promote
    truth, grant progress, execute tools, or affect completion authority.
    """

    def _record_model_boundary_telemetry(self, *, attempt: int) -> None:
        controller = self.controller
        compile_data = getattr(controller, "last_context_compile", None)
        decode_data = getattr(controller, "last_protocol_decode", None)

        if isinstance(compile_data, dict):
            payload: dict[str, Any] = {
                "attempt": attempt,
                "telemetry": dict(compile_data),
                "authority": "diagnostic_only",
            }
            self.log("model.context_compile", payload)

        if isinstance(decode_data, dict):
            payload = {
                "attempt": attempt,
                "telemetry": dict(decode_data),
                "authority": "diagnostic_only",
            }
            self.log("model.protocol_decode", payload)
            if bool(decode_data.get("lexical_repaired")):
                self.metrics["model_protocol_lexical_repairs"] = (
                    int(self.metrics.get("model_protocol_lexical_repairs", 0)) + 1
                )

        model = getattr(controller, "model", None)
        snapshot_fn = getattr(model, "telemetry_snapshot", None)
        if callable(snapshot_fn):
            try:
                gateway_data = snapshot_fn()
            except Exception:
                gateway_data = None
            if isinstance(gateway_data, dict):
                self.log("model.gateway_telemetry", {
                    "attempt": attempt,
                    "telemetry": dict(gateway_data),
                    "authority": "diagnostic_only",
                })

    def step_once(self) -> bool:
        controller = self.controller
        before = getattr(controller, "model_attempt_sequence", None)
        result = super().step_once()
        after = getattr(controller, "model_attempt_sequence", None)
        if isinstance(after, int) and after != before:
            # The controller-local sequence is only an invocation detector. The
            # durable attempt ID comes from metrics because runtime_meta restores
            # metrics across resume, while a new LLMController starts its local
            # sequence at zero.
            attempt = int(self.metrics.get("model_attempts", 0)) + 1
            self.metrics["model_attempts"] = attempt
            self._record_model_boundary_telemetry(attempt=attempt)
        return result
