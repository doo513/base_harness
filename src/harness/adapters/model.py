from dataclasses import dataclass
from typing import Any

from harness.model_gateway import ModelGateway


@dataclass
class ModelProfile:
    name: str
    max_context_tokens: int | None = None
    prefers_direct_execution: bool = True
    planner_threshold: str = "complex"
    metadata: dict[str, Any] | None = None


class CommandModelAdapter:
    """Backward-compatible command adapter backed by the Model Gateway.

    The command receives JSON with `system` and `user` on stdin and must print
    one harness Decision JSON object on stdout. Execution is argv-based through
    the gateway; it no longer uses `shell=True`.
    """

    def __init__(self, command: str, timeout_seconds: float = 120):
        self.command = command
        self.timeout_seconds = float(timeout_seconds)
        self.gateway = ModelGateway.single_command(command, timeout_seconds=self.timeout_seconds)

    @property
    def revision(self) -> str:
        return self.gateway.revision

    def telemetry_snapshot(self) -> dict[str, Any]:
        return self.gateway.telemetry_snapshot()

    def complete(self, *, system: str, user: str) -> str:
        return self.gateway.complete(system=system, user=user)
