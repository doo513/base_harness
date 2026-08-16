from __future__ import annotations

import json
import math
from typing import Any

from .failures import Failure, FailureKind
from .progress import ProgressEvent, ProgressKind, decision_progress_signatures
from .storage import ArtifactStore, IntegrityError, canonical_hash


class RuntimeProgressMixin:
    """Deterministic Actor progress accounting.

    Activity novelty is recorded but has zero reset authority. Progress-reset
    authority is reserved for trusted deterministic epistemic/task transitions.
    Profile task authority is deliberately monotonic: milestone removal, score
    decrease, or authority activation/deactivation during a turn cannot reset a
    no-progress horizon.
    """

    TASK_PROGRESS_SNAPSHOT_MAX_BYTES = 65_536
    TASK_PROGRESS_MAX_MILESTONES = 256
    TASK_PROGRESS_MAX_MILESTONE_CHARS = 512

    def _sync_progress_generation(self) -> bool:
        progress = self.state.progress
        generation = int(self.state.strategy_generation)
        if progress.strategy_generation == generation:
            return False
        progress.strategy_generation = generation
        progress.no_progress_streak = 0
        progress.last_family_signature = None
        progress.family_repeat_count = 0
        return True

    def _progress_facts_hash(self) -> str:
        content = {
            key: {
                "value": claim.value,
                "status": claim.status.value,
                "authority": claim.authority.value,
            }
            for key, claim in sorted(self.state.facts.items())
        }
        return canonical_hash(content)

    def _task_progress_snapshot(self) -> dict[str, Any] | None:
        hook = getattr(self.profile, "task_progress_snapshot", None)
        if hook is None:
            return None

        state_before = canonical_hash(self.state.snapshot())
        raw = hook(goal=self.goal, state=self.state)
        state_after = canonical_hash(self.state.snapshot())
        if state_before != state_after:
            raise IntegrityError("profile task_progress_snapshot mutated durable harness state")
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise IntegrityError("profile task_progress_snapshot must be an object or None")
        unknown = set(raw) - {"milestones", "score"}
        if unknown:
            raise IntegrityError(
                "profile task_progress_snapshot contains unsupported fields: "
                + ", ".join(sorted(str(key) for key in unknown))
            )

        milestones_raw = raw.get("milestones", [])
        if not isinstance(milestones_raw, list):
            raise IntegrityError("task progress milestones must be a list of strings")
        if len(milestones_raw) > self.TASK_PROGRESS_MAX_MILESTONES:
            raise IntegrityError("task progress milestone count exceeds configured bound")
        milestones: list[str] = []
        seen: set[str] = set()
        for index, item in enumerate(milestones_raw):
            if not isinstance(item, str) or not item.strip():
                raise IntegrityError(f"task progress milestone[{index}] must be a non-empty string")
            if len(item) > self.TASK_PROGRESS_MAX_MILESTONE_CHARS:
                raise IntegrityError(f"task progress milestone[{index}] exceeds configured bound")
            if item in seen:
                raise IntegrityError("task progress milestones must be unique")
            seen.add(item)
            milestones.append(item)

        score_raw = raw.get("score", 0.0)
        if isinstance(score_raw, bool) or not isinstance(score_raw, (int, float)):
            raise IntegrityError("task progress score must be a finite non-negative number")
        score = float(score_raw)
        if not math.isfinite(score) or score < 0.0:
            raise IntegrityError("task progress score must be a finite non-negative number")

        normalized = {
            "milestones": sorted(milestones),
            "score": score,
        }
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(encoded) > self.TASK_PROGRESS_SNAPSHOT_MAX_BYTES:
            raise IntegrityError(
                "profile task_progress_snapshot exceeds deterministic snapshot byte bound"
            )
        return normalized

    @staticmethod
    def _digest_prefix_from_artifact_ref(ref: str) -> str:
        try:
            return ArtifactStore.digest_from_ref(ref)
        except (ValueError, IntegrityError) as exc:
            raise IntegrityError(f"progress evidence artifact ref is invalid: {exc}") from exc

    def _verified_observation_fingerprint(self, ref: str) -> str:
        try:
            raw = self.artifacts.verified_read_bytes(ref)
        except (ValueError, IntegrityError) as exc:
            raise IntegrityError(f"progress evidence artifact cannot be verified: {exc}") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntegrityError(f"progress evidence artifact JSON cannot be decoded: {exc}") from exc
        if not isinstance(payload, dict):
            raise IntegrityError("progress evidence artifact payload is not an object")
        if payload.get("ok") is not True:
            raise IntegrityError("successful observation points to a non-success artifact payload")
        return canonical_hash(payload)

    def _known_successful_observation_fingerprints(self) -> set[str]:
        fingerprints: set[str] = set()
        for observation in self.state.observations:
            if not observation.ok or observation.artifact_ref is None:
                continue
            fingerprints.add(self._verified_observation_fingerprint(observation.artifact_ref))
        return fingerprints

    def _progress_baseline(self) -> dict[str, Any]:
        facts_hash = self._progress_facts_hash()
        task_progress_snapshot = self._task_progress_snapshot()
        successful_fingerprints = self._known_successful_observation_fingerprints()
        generation_reset = self._sync_progress_generation()
        return {
            "facts_hash": facts_hash,
            "task_progress_snapshot": task_progress_snapshot,
            "observation_count": len(self.state.observations),
            "successful_fingerprints": successful_fingerprints,
            "strategy_generation": int(self.state.strategy_generation),
            "generation_reset": generation_reset,
        }

    def _evaluate_actor_progress(
        self,
        decision,
        baseline: dict[str, Any],
        *,
        allow_trigger: bool,
    ) -> dict[str, Any]:
        progress = self.state.progress
        generation = int(self.state.strategy_generation)
        family_signature, exact_signature = decision_progress_signatures(decision)

        signals: list[ProgressEvent] = []
        reasons: list[str] = []
        if self._progress_facts_hash() != baseline["facts_hash"]:
            signals.append(ProgressEvent(
                ProgressKind.EPISTEMIC,
                source="verified_fact_content_changed",
                credit=1.0,
                verified=True,
                goal_relation="not_inferred",
            ))
            reasons.append("verified_fact_content_changed")

        task_before = baseline.get("task_progress_snapshot")
        task_after = self._task_progress_snapshot()
        if (task_before is None) != (task_after is None):
            raise IntegrityError(
                "profile task progress authority changed availability during one Actor transition"
            )
        task_regression: dict[str, Any] | None = None
        if task_before is not None and task_after is not None:
            before_milestones = set(task_before["milestones"])
            after_milestones = set(task_after["milestones"])
            removed = sorted(before_milestones - after_milestones)
            added = sorted(after_milestones - before_milestones)
            before_score = float(task_before["score"])
            after_score = float(task_after["score"])
            score_decreased = after_score < before_score
            score_increased = after_score > before_score

            if removed or score_decreased:
                task_regression = {
                    "removed_milestones": removed,
                    "before_score": before_score,
                    "after_score": after_score,
                    "added_milestones_ignored_for_credit": added,
                }
                self.log("progress.task_regression", dict(task_regression))
            elif added or score_increased:
                signals.append(ProgressEvent(
                    ProgressKind.TASK,
                    source="profile_task_progress_advanced",
                    credit=1.0,
                    verified=True,
                    goal_relation="profile_explicit_monotonic",
                    details={
                        "added_milestones": added,
                        "before_score": before_score,
                        "after_score": after_score,
                        "snapshot_bytes_bound": self.TASK_PROGRESS_SNAPSHOT_MAX_BYTES,
                    },
                ))
                reasons.append("profile_task_progress_advanced")

        prior_fingerprints = set(baseline["successful_fingerprints"])
        novel_fingerprints: list[str] = []
        novel_refs: list[str] = []
        start = int(baseline["observation_count"])
        for observation in self.state.observations[start:]:
            if not observation.ok:
                continue
            if observation.artifact_ref is None:
                raise IntegrityError("successful observation is missing artifact_ref")
            fingerprint = self._verified_observation_fingerprint(observation.artifact_ref)
            if fingerprint not in prior_fingerprints and fingerprint not in novel_fingerprints:
                novel_fingerprints.append(fingerprint)
                novel_refs.append(observation.artifact_ref)
        if novel_fingerprints:
            signals.append(ProgressEvent(
                ProgressKind.ACTIVITY,
                source="novel_successful_observation_content",
                credit=0.0,
                verified=False,
                evidence_refs=tuple(novel_refs),
                goal_relation="unknown",
                details={"fingerprints": list(novel_fingerprints)},
            ))

        for signal in signals:
            if signal.kind == ProgressKind.ACTIVITY:
                progress.activity_events += 1
            elif signal.kind == ProgressKind.EPISTEMIC:
                progress.epistemic_events += 1
            elif signal.kind == ProgressKind.TASK:
                progress.task_events += 1
            self.log("progress.signal", signal.dump())

        max_credit = max((signal.credit for signal in signals), default=0.0)
        made_progress = max_credit >= self.progress_policy.reset_credit_threshold
        progress.evaluations += 1
        self.metrics["progress_evaluations"] = int(self.metrics.get("progress_evaluations", 0)) + 1

        trigger: str | None = None
        failure: Failure | None = None

        if made_progress:
            progress.progress_events += 1
            progress.no_progress_streak = 0
            progress.last_family_signature = None
            progress.family_repeat_count = 0
            progress.last_progress_step = int(self.state.step)
            progress.last_progress_generation = generation
            progress.last_progress_reasons = list(reasons)
            self.metrics["progress_events"] = int(self.metrics.get("progress_events", 0)) + 1
        else:
            progress.no_progress_streak += 1
            if progress.last_family_signature == family_signature:
                progress.family_repeat_count += 1
            else:
                progress.last_family_signature = family_signature
                progress.family_repeat_count = 1

            if allow_trigger:
                generations_without_progress = generation - int(progress.last_progress_generation)
                if generations_without_progress >= self.progress_policy.max_strategy_generations_without_progress:
                    trigger = "strategy_exhausted"
                    failure = Failure(
                        FailureKind.STRATEGY_EXHAUSTED,
                        (
                            "progress control exhausted strategy generations without recognized progress: "
                            f"generation={generation}, last_progress_generation={progress.last_progress_generation}"
                        ),
                        action="stage6:strategy_exhausted",
                        signature_key="stage6:strategy_exhausted",
                    )
                elif progress.family_repeat_count >= self.progress_policy.family_repeat_limit:
                    trigger = "family_repeat"
                    failure = Failure(
                        FailureKind.NO_PROGRESS,
                        f"repeated Actor decision family produced no recognized progress: {family_signature}",
                        action=family_signature,
                        signature_key=f"stage6:family:{family_signature}",
                    )
                elif progress.no_progress_streak >= self.progress_policy.no_progress_streak_limit:
                    trigger = "global_streak"
                    failure = Failure(
                        FailureKind.NO_PROGRESS,
                        (
                            "consecutive Actor decisions produced no recognized progress: "
                            f"streak={progress.no_progress_streak}; latest_family={family_signature}"
                        ),
                        action="stage6:global_no_progress",
                        signature_key="stage6:global_no_progress",
                    )

                if failure is not None:
                    progress.threshold_triggers += 1
                    self.metrics["no_progress_triggers"] = int(self.metrics.get("no_progress_triggers", 0)) + 1
                    if failure.kind == FailureKind.STRATEGY_EXHAUSTED:
                        self.metrics["strategy_exhaustions"] = int(self.metrics.get("strategy_exhaustions", 0)) + 1
                    else:
                        progress.no_progress_streak = 0
                        progress.last_family_signature = None
                        progress.family_repeat_count = 0
                    self.fail(failure)

        payload = {
            "decision_kind": decision.kind,
            "family_signature": family_signature,
            "exact_signature": exact_signature,
            "made_progress": made_progress,
            "progress_reasons": list(reasons),
            "progress_signals": [signal.dump() for signal in signals],
            "max_credit": max_credit,
            "reset_credit_threshold": self.progress_policy.reset_credit_threshold,
            "task_progress_before": task_before,
            "task_progress_after": task_after,
            "task_progress_regression": task_regression,
            "novel_successful_observation_fingerprints": novel_fingerprints,
            "strategy_generation": generation,
            "generation_reset": bool(baseline.get("generation_reset", False)),
            "no_progress_streak": progress.no_progress_streak,
            "family_repeat_count": progress.family_repeat_count,
            "trigger": trigger,
            "trigger_allowed": bool(allow_trigger),
            "specific_failure_precedence": not allow_trigger,
        }
        self.log("progress.evaluated", payload)
        return payload
