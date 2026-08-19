from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentControlError(ValueError):
    pass


class AgentTaskStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    BLOCKED = "blocked"


@dataclass
class AgentTask:
    id: str
    title: str
    depends_on: tuple[str, ...] = ()
    status: AgentTaskStatus = AgentTaskStatus.PENDING
    note: str | None = None

    def dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "depends_on": list(self.depends_on),
            "status": self.status.value,
            "note": self.note,
        }

    @classmethod
    def load(cls, raw: dict[str, Any]) -> "AgentTask":
        return cls(
            id=str(raw.get("id", "")),
            title=str(raw.get("title", "")),
            depends_on=tuple(str(item) for item in raw.get("depends_on", [])),
            status=AgentTaskStatus(raw.get("status", AgentTaskStatus.PENDING.value)),
            note=(str(raw["note"]) if raw.get("note") is not None else None),
        )


@dataclass
class AgentControlState:
    """Durable actor workflow state with no truth/progress/completion authority."""

    MAX_TASKS = 64
    MAX_OBJECTIVE_CHARS = 4000
    MAX_TITLE_CHARS = 800
    MAX_NOTE_CHARS = 1600

    objective: str | None = None
    tasks: dict[str, AgentTask] = field(default_factory=dict)
    active_task_id: str | None = None
    revision: int = 0

    @staticmethod
    def _require_text(value: Any, *, name: str, limit: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise AgentControlError(f"{name} must be a non-empty string")
        text = value.strip()
        if len(text) > limit:
            raise AgentControlError(f"{name} exceeds {limit} characters")
        return text

    @classmethod
    def _validate_graph(cls, tasks: dict[str, AgentTask]) -> None:
        for task in tasks.values():
            missing = [dep for dep in task.depends_on if dep not in tasks]
            if missing:
                raise AgentControlError(
                    f"task {task.id!r} depends on unknown tasks: {', '.join(missing)}"
                )
            if task.id in task.depends_on:
                raise AgentControlError(f"task {task.id!r} cannot depend on itself")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise AgentControlError("task dependency graph contains a cycle")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dep in tasks[task_id].depends_on:
                visit(dep)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in sorted(tasks):
            visit(task_id)

    def replace_plan(self, objective: Any, raw_tasks: Any) -> None:
        objective_text = self._require_text(
            objective, name="plan objective", limit=self.MAX_OBJECTIVE_CHARS
        )
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise AgentControlError("plan tasks must be a non-empty list")
        if len(raw_tasks) > self.MAX_TASKS:
            raise AgentControlError(f"plan exceeds maximum task count {self.MAX_TASKS}")

        tasks: dict[str, AgentTask] = {}
        for index, raw in enumerate(raw_tasks):
            if not isinstance(raw, dict):
                raise AgentControlError(f"plan task[{index}] must be an object")
            task_id = self._require_text(raw.get("id"), name=f"task[{index}].id", limit=128)
            title = self._require_text(raw.get("title"), name=f"task[{index}].title", limit=self.MAX_TITLE_CHARS)
            if task_id in tasks:
                raise AgentControlError(f"duplicate task id: {task_id}")
            deps_raw = raw.get("depends_on", [])
            if not isinstance(deps_raw, list) or any(not isinstance(dep, str) or not dep.strip() for dep in deps_raw):
                raise AgentControlError(f"task[{index}].depends_on must be a list of task ids")
            deps = tuple(dep.strip() for dep in deps_raw)
            if len(deps) != len(set(deps)):
                raise AgentControlError(f"task[{index}] has duplicate dependencies")
            tasks[task_id] = AgentTask(id=task_id, title=title, depends_on=deps)

        self._validate_graph(tasks)
        self.objective = objective_text
        self.tasks = tasks
        self.active_task_id = None
        self.revision += 1

    def _task(self, task_id: Any) -> AgentTask:
        task_key = self._require_text(task_id, name="task id", limit=128)
        task = self.tasks.get(task_key)
        if task is None:
            raise AgentControlError(f"unknown task id: {task_key}")
        return task

    def activate(self, task_id: Any) -> None:
        task = self._task(task_id)
        unfinished = [
            dep for dep in task.depends_on
            if self.tasks[dep].status != AgentTaskStatus.DONE
        ]
        if unfinished:
            raise AgentControlError(
                f"task {task.id!r} has unfinished dependencies: {', '.join(unfinished)}"
            )
        if task.status == AgentTaskStatus.DONE:
            raise AgentControlError("completed task cannot be reactivated")
        if self.active_task_id is not None and self.active_task_id in self.tasks:
            current = self.tasks[self.active_task_id]
            if current.status == AgentTaskStatus.ACTIVE:
                current.status = AgentTaskStatus.PENDING
        task.status = AgentTaskStatus.ACTIVE
        self.active_task_id = task.id
        self.revision += 1

    def update(self, task_id: Any, *, status: Any, note: Any = None) -> None:
        task = self._task(task_id)
        try:
            new_status = AgentTaskStatus(status)
        except ValueError as exc:
            raise AgentControlError(f"unsupported task status: {status!r}") from exc
        if new_status == AgentTaskStatus.ACTIVE:
            self.activate(task.id)
            if note is not None:
                task.note = self._require_text(note, name="task note", limit=self.MAX_NOTE_CHARS)
            return
        if note is not None:
            task.note = self._require_text(note, name="task note", limit=self.MAX_NOTE_CHARS)
        task.status = new_status
        if self.active_task_id == task.id:
            self.active_task_id = None
        self.revision += 1

    def dump(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "tasks": {key: task.dump() for key, task in sorted(self.tasks.items())},
            "active_task_id": self.active_task_id,
            "revision": int(self.revision),
        }

    def context_view(self) -> dict[str, Any]:
        return {
            "trust": "actor_workflow_state",
            "instruction_authority": "none",
            "progress_authority": False,
            "completion_authority": False,
            **self.dump(),
        }

    @classmethod
    def load(cls, raw: Any) -> "AgentControlState":
        if not isinstance(raw, dict):
            return cls()
        tasks_raw = raw.get("tasks", {})
        if not isinstance(tasks_raw, dict):
            raise AgentControlError("persisted agent tasks must be an object")
        state = cls(
            objective=(str(raw["objective"]) if raw.get("objective") is not None else None),
            tasks={str(key): AgentTask.load(value) for key, value in tasks_raw.items()},
            active_task_id=(str(raw["active_task_id"]) if raw.get("active_task_id") is not None else None),
            revision=int(raw.get("revision", 0)),
        )
        if len(state.tasks) > cls.MAX_TASKS:
            raise AgentControlError("persisted agent task count exceeds bound")
        cls._validate_graph(state.tasks)
        if state.active_task_id is not None:
            active = state.tasks.get(state.active_task_id)
            if active is None or active.status != AgentTaskStatus.ACTIVE:
                raise AgentControlError("persisted active task pointer is inconsistent")
        return state
