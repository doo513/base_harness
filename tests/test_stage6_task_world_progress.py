from __future__ import annotations

from pathlib import Path

import pytest

from harness.core.context import ContextPolicy
from harness.core.contracts import GoalContract
from harness.core.controller import Decision
from harness.core.progress import ProgressPolicy
from harness.core.runtime_progress import RuntimeProgressMixin
from harness.core.state import HarnessState
from harness.core.storage import ArtifactStore, IntegrityError
from harness.profiles.base import DomainProfile


class BaseProgressProfile(DomainProfile):
    name = "task-progress-test"

    def default_goal(self):
        return GoalContract(goal="reach milestone", acceptance=["milestone reached"])


class CompletionMilestoneProfile(BaseProgressProfile):
    def task_progress_snapshot(self, *, goal, state):
        return {"completion_milestone": bool(state.completed)}


class MutatingSnapshotProfile(BaseProgressProfile):
    def task_progress_snapshot(self, *, goal, state):
        state.completed = True
        return {"completion_milestone": True}


class OpaqueSnapshotProfile(BaseProgressProfile):
    def task_progress_snapshot(self, *, goal, state):
        return {"opaque": object()}


class ProgressHarness(RuntimeProgressMixin):
    def __init__(self, tmp_path: Path, profile: DomainProfile):
        self.profile = profile
        self.goal = profile.default_goal()
        self.state = HarnessState()
        self.progress_policy = ProgressPolicy()
        self.context_policy = ContextPolicy()
        self.metrics = {"progress_evaluations": 0, "progress_events": 0}
        self.artifacts = ArtifactStore(tmp_path / "artifacts")
        self.logged = []
        self.failures = []

    def log(self, kind, payload):
        self.logged.append((kind, payload))

    def fail(self, failure):
        self.failures.append(failure)


def test_profile_explicit_task_snapshot_delta_grants_task_progress(tmp_path):
    harness = ProgressHarness(tmp_path, CompletionMilestoneProfile())
    baseline = harness._progress_baseline()
    harness.state.completed = True

    result = harness._evaluate_actor_progress(
        Decision("complete", {"reason": "milestone"}),
        baseline,
        allow_trigger=True,
    )

    assert result["made_progress"] is True
    assert "profile_task_progress_snapshot_changed" in result["progress_reasons"]
    assert harness.state.progress.task_events == 1
    assert harness.state.progress.progress_events == 1


def test_default_profile_grants_no_task_progress_authority(tmp_path):
    harness = ProgressHarness(tmp_path, BaseProgressProfile())
    baseline = harness._progress_baseline()
    harness.state.completed = True

    result = harness._evaluate_actor_progress(
        Decision("complete", {"reason": "no explicit task snapshot"}),
        baseline,
        allow_trigger=False,
    )

    assert all(
        signal["kind"] != "task" for signal in result["progress_signals"]
    )
    assert harness.state.progress.task_events == 0


def test_task_progress_snapshot_must_be_pure(tmp_path):
    harness = ProgressHarness(tmp_path, MutatingSnapshotProfile())
    with pytest.raises(IntegrityError, match="mutated durable harness state"):
        harness._progress_baseline()


def test_task_progress_snapshot_must_be_deterministic_json(tmp_path):
    harness = ProgressHarness(tmp_path, OpaqueSnapshotProfile())
    with pytest.raises(IntegrityError, match="not deterministic JSON"):
        harness._progress_baseline()


def test_task_progress_snapshot_is_bounded(tmp_path):
    class HugeSnapshotProfile(BaseProgressProfile):
        def task_progress_snapshot(self, *, goal, state):
            return {"blob": "x" * (RuntimeProgressMixin.TASK_PROGRESS_SNAPSHOT_MAX_BYTES + 1)}

    harness = ProgressHarness(tmp_path, HugeSnapshotProfile())
    with pytest.raises(IntegrityError, match="exceeds deterministic snapshot byte bound"):
        harness._progress_baseline()
