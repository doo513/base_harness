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
        return {
            "milestones": ["completed"] if state.completed else [],
            "score": 1 if state.completed else 0,
        }


class MutatingSnapshotProfile(BaseProgressProfile):
    def task_progress_snapshot(self, *, goal, state):
        state.completed = True
        return {"milestones": ["completed"], "score": 1}


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


def test_profile_explicit_monotonic_task_advance_grants_progress(tmp_path):
    harness = ProgressHarness(tmp_path, CompletionMilestoneProfile())
    baseline = harness._progress_baseline()
    harness.state.completed = True

    result = harness._evaluate_actor_progress(
        Decision("complete", {"reason": "milestone"}),
        baseline,
        allow_trigger=True,
    )

    assert result["made_progress"] is True
    assert "profile_task_progress_advanced" in result["progress_reasons"]
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

    assert all(signal["kind"] != "task" for signal in result["progress_signals"])
    assert harness.state.progress.task_events == 0


def test_task_progress_regression_does_not_grant_credit(tmp_path):
    harness = ProgressHarness(tmp_path, CompletionMilestoneProfile())
    harness.state.completed = True
    baseline = harness._progress_baseline()
    harness.state.completed = False

    result = harness._evaluate_actor_progress(
        Decision("complete", {"reason": "regressed"}),
        baseline,
        allow_trigger=False,
    )

    assert result["made_progress"] is False
    assert result["task_progress_regression"] is not None
    assert result["task_progress_regression"]["removed_milestones"] == ["completed"]
    assert harness.state.progress.task_events == 0


def test_score_decrease_is_not_progress_even_without_milestone_removal(tmp_path):
    class ScoreProfile(BaseProgressProfile):
        def task_progress_snapshot(self, *, goal, state):
            score = 1 if state.completed else 0
            return {"milestones": [], "score": score}

    harness = ProgressHarness(tmp_path, ScoreProfile())
    harness.state.completed = True
    baseline = harness._progress_baseline()
    harness.state.completed = False
    result = harness._evaluate_actor_progress(
        Decision("complete", {"reason": "score decreased"}), baseline, allow_trigger=False
    )
    assert result["made_progress"] is False
    assert result["task_progress_regression"]["before_score"] == 1.0
    assert result["task_progress_regression"]["after_score"] == 0.0


def test_task_progress_snapshot_must_be_pure(tmp_path):
    harness = ProgressHarness(tmp_path, MutatingSnapshotProfile())
    with pytest.raises(IntegrityError, match="mutated durable harness state"):
        harness._progress_baseline()


def test_task_progress_snapshot_rejects_unsupported_schema(tmp_path):
    harness = ProgressHarness(tmp_path, OpaqueSnapshotProfile())
    with pytest.raises(IntegrityError, match="unsupported fields"):
        harness._progress_baseline()


def test_task_progress_snapshot_is_bounded(tmp_path):
    class HugeSnapshotProfile(BaseProgressProfile):
        def task_progress_snapshot(self, *, goal, state):
            return {
                "milestones": [
                    "x" * (RuntimeProgressMixin.TASK_PROGRESS_MAX_MILESTONE_CHARS + 1)
                ],
                "score": 0,
            }

    harness = ProgressHarness(tmp_path, HugeSnapshotProfile())
    with pytest.raises(IntegrityError, match=r"milestone\[0\] exceeds configured bound"):
        harness._progress_baseline()


def test_task_progress_authority_cannot_toggle_during_transition(tmp_path):
    class ToggleAuthorityProfile(BaseProgressProfile):
        def task_progress_snapshot(self, *, goal, state):
            if state.completed:
                return {"milestones": ["completed"], "score": 1}
            return None

    harness = ProgressHarness(tmp_path, ToggleAuthorityProfile())
    baseline = harness._progress_baseline()
    harness.state.completed = True
    with pytest.raises(IntegrityError, match="changed availability"):
        harness._evaluate_actor_progress(
            Decision("complete", {"reason": "toggle"}), baseline, allow_trigger=False
        )
