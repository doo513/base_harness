from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(frozen=True)
class GoalContract:
    """Task goal plus harness-side acceptance requirements.

    The actor may request completion, but it cannot change these fields. Mandatory
    control semantics are retained exactly; oversized contracts fail closed at
    task entry instead of being silently truncated by context projection.
    """

    MAX_GOAL_CHARS: ClassVar[int] = 16_000
    MAX_CRITERIA_ITEMS: ClassVar[int] = 64
    MAX_CRITERION_CHARS: ClassVar[int] = 4_000
    MAX_TOTAL_MANDATORY_CHARS: ClassVar[int] = 64_000
    MAX_TASK_ID_CHARS: ClassVar[int] = 256

    goal: str
    acceptance: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    pinned_constraints: list[str] = field(default_factory=list)
    task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def limits_descriptor(cls) -> dict[str, int | str]:
        return {
            "schema_version": "goal-contract-limits-v1",
            "max_goal_chars": cls.MAX_GOAL_CHARS,
            "max_criteria_items_per_field": cls.MAX_CRITERIA_ITEMS,
            "max_criterion_chars": cls.MAX_CRITERION_CHARS,
            "max_total_mandatory_chars": cls.MAX_TOTAL_MANDATORY_CHARS,
            "max_task_id_chars": cls.MAX_TASK_ID_CHARS,
            "overflow_mode": "fail_closed_before_run_creation",
        }

    @staticmethod
    def _validate_text_list(name: str, values: Any) -> list[str]:
        if not isinstance(values, list):
            raise ValueError(f"{name} must be a list of strings")
        if len(values) > GoalContract.MAX_CRITERIA_ITEMS:
            raise ValueError(
                f"{name} exceeds max items={GoalContract.MAX_CRITERIA_ITEMS}"
            )
        checked: list[str] = []
        for index, value in enumerate(values):
            if not isinstance(value, str):
                raise ValueError(f"{name}[{index}] must be a string")
            if not value.strip():
                raise ValueError(f"{name}[{index}] must not be empty")
            if len(value) > GoalContract.MAX_CRITERION_CHARS:
                raise ValueError(
                    f"{name}[{index}] exceeds max chars={GoalContract.MAX_CRITERION_CHARS}"
                )
            checked.append(value)
        return checked

    def validate(self) -> None:
        if not isinstance(self.goal, str) or not self.goal.strip():
            raise ValueError("goal must not be empty")
        if len(self.goal) > self.MAX_GOAL_CHARS:
            raise ValueError(f"goal exceeds max chars={self.MAX_GOAL_CHARS}")

        acceptance = self._validate_text_list("acceptance", self.acceptance)
        constraints = self._validate_text_list("constraints", self.constraints)
        pinned = self._validate_text_list("pinned_constraints", self.pinned_constraints)
        if not acceptance:
            raise ValueError("at least one acceptance criterion is required")

        if self.task_id is not None:
            if not isinstance(self.task_id, str) or not self.task_id.strip():
                raise ValueError("task_id must be a non-empty string when supplied")
            if len(self.task_id) > self.MAX_TASK_ID_CHARS:
                raise ValueError(f"task_id exceeds max chars={self.MAX_TASK_ID_CHARS}")

        total_chars = len(self.goal) + sum(
            len(item) for item in acceptance + constraints + pinned
        )
        if total_chars > self.MAX_TOTAL_MANDATORY_CHARS:
            raise ValueError(
                "mandatory goal/control text exceeds total bound="
                f"{self.MAX_TOTAL_MANDATORY_CHARS}"
            )
