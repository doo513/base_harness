from dataclasses import dataclass
from typing import Any
import subprocess

@dataclass
class ModelProfile:
    name: str
    max_context_tokens: int | None = None
    prefers_direct_execution: bool = True
    planner_threshold: str = "complex"
    metadata: dict[str, Any] | None = None

class CommandModelAdapter:
    """Use any local model/agent command as a controller backend.

    The command receives a JSON object with `system` and `user` on stdin and must
    print one harness Decision JSON object on stdout.
    """
    def __init__(self, command: str, timeout_seconds: float = 120):
        self.command = command
        self.timeout_seconds = timeout_seconds

    def complete(self, *, system: str, user: str) -> str:
        import json
        proc = subprocess.run(
            self.command,
            shell=True,
            input=json.dumps({"system": system, "user": user}, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"model command failed ({proc.returncode}): {proc.stderr[-2000:]}")
        return proc.stdout.strip()
