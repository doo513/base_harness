from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class GoalContract:
    """Task goal plus harness-side acceptance requirements.

    The actor may request completion, but it cannot change these fields.
    """
    goal: str
    acceptance: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    pinned_constraints: list[str] = field(default_factory=list)
    task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.goal.strip():
            raise ValueError("goal must not be empty")
        if not self.acceptance:
            raise ValueError("at least one acceptance criterion is required")
