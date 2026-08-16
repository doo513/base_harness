from dataclasses import dataclass
import time

@dataclass
class Budget:
    hard_max_steps: int = 100
    hard_wall_seconds: float = 3600
    soft_max_steps: int | None = None

    def start(self): return time.monotonic()

    def hard_exceeded(self, step, started_at):
        return step >= self.hard_max_steps or (time.monotonic()-started_at) >= self.hard_wall_seconds
