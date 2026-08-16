from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

from .storage import canonical_hash, canonical_json


_ARTIFACT_RE = re.compile(r"^artifact://([0-9a-f]{64})_.+$")


class ContextProjection(dict):
    """Namespaced governed context with non-serialized legacy read aliases.

    The built-in LLM JSON serialization sees only the actual namespaced keys.
    Existing in-process trusted Controller adapters can continue read-only
    access to the previous top-level keys during the Stage-07 transition.
    """

    _LEGACY_PATHS = {
        "pinned_constraints": ("goal_contract", "pinned_constraints"),
        "acceptance": ("goal_contract", "acceptance"),
        "facts": ("trusted", "facts"),
        "hypotheses": ("untrusted", "hypotheses"),
        "refuted_hypotheses": ("untrusted", "refuted_hypotheses"),
        "unknowns": ("untrusted", "unknowns"),
        "observations": ("untrusted", "observations"),
        "recent_failures": ("control", "recent_failures"),
        "recovery_directive": ("control", "recovery_directive"),
        "strategy_generation": ("control", "strategy_generation"),
        "recovery_halted": ("control", "recovery_halted"),
        "progress": ("control", "progress"),
        "tools": ("tools",),
    }

    def _legacy_value(self, key: str):
        path = self._LEGACY_PATHS.get(key)
        if path is None:
            raise KeyError(key)
        value: Any = self
        for part in path:
            value = dict.__getitem__(value, part) if isinstance(value, ContextProjection) else value[part]
        return value

    def __getitem__(self, key):
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            return self._legacy_value(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        return dict.__contains__(self, key) or key in self._LEGACY_PATHS


@dataclass(frozen=True)
class ContextPolicy:
    max_observations: int = 12
    max_preview_chars_per_observation: int = 1200
    max_total_observation_preview_chars: int = 6000
    max_hypotheses: int = 20
    max_refuted_hypotheses: int = 10
    max_unknowns: int = 20
    max_recent_failures: int = 5
    max_tool_description_chars: int = 500
    max_failure_message_chars: int = 800
    max_speculative_value_chars: int = 1200
    max_unknown_chars: int = 500
    max_evidence_refs_per_claim: int = 8

    def __post_init__(self) -> None:
        integer_fields = (
            "max_observations",
            "max_preview_chars_per_observation",
            "max_total_observation_preview_chars",
            "max_hypotheses",
            "max_refuted_hypotheses",
            "max_unknowns",
            "max_recent_failures",
            "max_tool_description_chars",
            "max_failure_message_chars",
            "max_speculative_value_chars",
            "max_unknown_chars",
            "max_evidence_refs_per_claim",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": "context-policy-v1",
            "max_observations": self.max_observations,
            "max_preview_chars_per_observation": self.max_preview_chars_per_observation,
            "max_total_observation_preview_chars": self.max_total_observation_preview_chars,
            "max_hypotheses": self.max_hypotheses,
            "max_refuted_hypotheses": self.max_refuted_hypotheses,
            "max_unknowns": self.max_unknowns,
            "max_recent_failures": self.max_recent_failures,
            "max_tool_description_chars": self.max_tool_description_chars,
            "max_failure_message_chars": self.max_failure_message_chars,
            "max_speculative_value_chars": self.max_speculative_value_chars,
            "max_unknown_chars": self.max_unknown_chars,
            "max_evidence_refs_per_claim": self.max_evidence_refs_per_claim,
            "mandatory_sections_lossy": False,
            "observation_duplicate_identity": "source_plus_content_address_digest",
            "untrusted_instruction_authority": "none",
            "valid_until_wall_clock_interpretation": False,
            "legacy_aliases_serialized_to_model": False,
        }


def _truncate_text(text: str, limit: int) -> tuple[str, bool]:
    if limit < 0:
        raise ValueError("text limit must be non-negative")
    if len(text) <= limit:
        return text, False
    if limit == 0:
        return "", bool(text)
    return text[:limit], True


def _render_data_preview(value: Any, limit: int) -> dict[str, Any]:
    if isinstance(value, str):
        raw = value
        fmt = "text"
    else:
        raw = canonical_json(value)
        fmt = "canonical_json"
    text, truncated = _truncate_text(raw, limit)
    return {
        "format": fmt,
        "text": text,
        "truncated": truncated,
        "original_chars": len(raw),
        "visible_chars": len(text),
    }


def _artifact_digest(ref: str | None) -> str | None:
    if not isinstance(ref, str):
        return None
    match = _ARTIFACT_RE.match(ref)
    return match.group(1) if match else None


class ContextProjector:
    """Pure deterministic projection from durable state to Actor-visible context."""

    schema_version = "context-projection-v1"

    def __init__(self, policy: ContextPolicy | None = None):
        self.policy = policy or ContextPolicy()

    def _project_claim(self, claim, *, trust: str) -> dict[str, Any]:
        preview = _render_data_preview(claim.value, self.policy.max_speculative_value_chars)
        refs = list(claim.evidence_refs)
        visible_refs = refs[: self.policy.max_evidence_refs_per_claim]
        return {
            "key": claim.key,
            "status": claim.status.value,
            "authority": claim.authority.value,
            "trust": trust,
            "instruction_authority": "none",
            "value_preview": preview,
            "evidence_refs": visible_refs,
            "omitted_evidence_ref_count": max(0, len(refs) - len(visible_refs)),
            "valid_until": claim.valid_until,
            "superseded_by": claim.superseded_by,
        }

    def _project_facts(self, state) -> tuple[dict[str, Any], list[str]]:
        current: dict[str, Any] = {}
        superseded: list[str] = []
        for key in sorted(state.facts):
            claim = state.facts[key]
            if claim.superseded_by is not None:
                superseded.append(key)
                continue
            dumped = claim.dump()
            dumped["trust"] = "verified_fact"
            dumped["instruction_authority"] = "none"
            current[key] = dumped
        return current, superseded

    def _select_claims(self, claims: dict[str, Any], limit: int, *, trust: str) -> tuple[dict[str, Any], int]:
        keys = sorted(claims)
        selected_keys = keys[:limit]
        projected = {key: self._project_claim(claims[key], trust=trust) for key in selected_keys}
        return projected, max(0, len(keys) - len(selected_keys))

    def _observation_identity(self, observation) -> str:
        digest = _artifact_digest(observation.artifact_ref)
        if digest is not None:
            return f"{observation.source}:{digest}"
        return f"{observation.source}:fallback:{canonical_hash({'ok': observation.ok, 'preview': observation.preview, 'error': observation.error})}"

    def _project_observations(self, observations: list[Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
        groups: dict[str, dict[str, Any]] = {}
        for index, observation in enumerate(observations):
            identity = self._observation_identity(observation)
            group = groups.get(identity)
            if group is None:
                groups[identity] = {
                    "identity": identity,
                    "occurrences": 1,
                    "first_step": int(observation.step),
                    "latest_step": int(observation.step),
                    "latest_index": index,
                    "representative": observation,
                }
                continue
            group["occurrences"] += 1
            group["first_step"] = min(group["first_step"], int(observation.step))
            if (int(observation.step), index) >= (group["latest_step"], group["latest_index"]):
                group["latest_step"] = int(observation.step)
                group["latest_index"] = index
                group["representative"] = observation

        ordered = sorted(groups.values(), key=lambda item: (-item["latest_step"], item["identity"]))
        selected = ordered[: self.policy.max_observations]
        remaining_chars = self.policy.max_total_observation_preview_chars
        projected: list[dict[str, Any]] = []

        for group in selected:
            observation = group["representative"]
            per_item_limit = min(self.policy.max_preview_chars_per_observation, remaining_chars)
            preview = _render_data_preview(observation.preview, per_item_limit)
            remaining_chars = max(0, remaining_chars - preview["visible_chars"])
            error_preview = None
            if observation.error is not None:
                error_preview = _render_data_preview(
                    str(observation.error),
                    min(self.policy.max_failure_message_chars, remaining_chars),
                )
                remaining_chars = max(0, remaining_chars - error_preview["visible_chars"])
            projected.append({
                "trust": "untrusted_observation",
                "instruction_authority": "none",
                "source": observation.source,
                "ok": bool(observation.ok),
                "first_step": group["first_step"],
                "latest_step": group["latest_step"],
                "occurrence_count": group["occurrences"],
                "artifact_ref": observation.artifact_ref,
                "preview": preview,
                "error_preview": error_preview,
            })

        stats = {
            "raw_observation_count": len(observations),
            "unique_observation_group_count": len(ordered),
            "selected_observation_group_count": len(selected),
            "omitted_observation_group_count": max(0, len(ordered) - len(selected)),
            "duplicate_observation_count_collapsed": max(0, len(observations) - len(ordered)),
            "visible_observation_preview_chars": self.policy.max_total_observation_preview_chars - remaining_chars,
        }
        return projected, stats

    def _project_failures(self, failures: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        selected = [] if self.policy.max_recent_failures == 0 else failures[-self.policy.max_recent_failures :]
        projected: list[dict[str, Any]] = []
        for record in selected:
            item = dict(record)
            message = str(item.get("message", ""))
            visible, truncated = _truncate_text(message, self.policy.max_failure_message_chars)
            item["message"] = visible
            item["message_truncated"] = truncated
            item["message_instruction_authority"] = "none"
            projected.append(item)
        return projected, max(0, len(failures) - len(selected))

    def _project_unknowns(self, unknowns: list[str]) -> tuple[list[dict[str, Any]], int]:
        selected = list(unknowns[-self.policy.max_unknowns :]) if self.policy.max_unknowns else []
        result: list[dict[str, Any]] = []
        for value in selected:
            visible, truncated = _truncate_text(str(value), self.policy.max_unknown_chars)
            result.append({
                "trust": "untrusted_unknown",
                "instruction_authority": "none",
                "text": visible,
                "truncated": truncated,
            })
        return result, max(0, len(unknowns) - len(selected))

    def _project_tools(self, tools: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in sorted(tools):
            spec = tools[name]
            description, truncated = _truncate_text(str(spec.description), self.policy.max_tool_description_chars)
            result[name] = {
                "description": description,
                "description_truncated": truncated,
                "side_effect": spec.side_effect.value,
                "idempotent": bool(spec.idempotent),
            }
        return result

    def project(self, *, goal, state, tools: dict[str, Any]) -> ContextProjection:
        current_facts, superseded_fact_keys = self._project_facts(state)
        hypotheses, omitted_hypotheses = self._select_claims(
            state.hypotheses, self.policy.max_hypotheses, trust="untrusted_speculation"
        )
        refuted, omitted_refuted = self._select_claims(
            state.refuted_hypotheses, self.policy.max_refuted_hypotheses,
            trust="untrusted_refuted_speculation",
        )
        observations, observation_stats = self._project_observations(state.observations)
        failures, omitted_failures = self._project_failures(state.failures)
        unknowns, omitted_unknowns = self._project_unknowns(state.unknowns)

        return ContextProjection({
            "schema_version": self.schema_version,
            "projection": {
                "policy": self.policy.descriptor(),
                "omissions": {
                    "hypotheses": omitted_hypotheses,
                    "refuted_hypotheses": omitted_refuted,
                    "unknowns": omitted_unknowns,
                    "failures": omitted_failures,
                    "observation_groups": observation_stats["omitted_observation_group_count"],
                },
                "observation_stats": observation_stats,
                "mandatory_sections_lossy": False,
                "projection_is_read_only": True,
                "legacy_aliases_model_visible": False,
            },
            "goal_contract": {
                "goal": goal.goal,
                "acceptance": list(goal.acceptance),
                "constraints": list(goal.constraints),
                "pinned_constraints": list(goal.pinned_constraints),
                "task_id": goal.task_id,
            },
            "trusted": {
                "facts": current_facts,
                "superseded_fact_keys": superseded_fact_keys,
            },
            "untrusted": {
                "hypotheses": hypotheses,
                "refuted_hypotheses": refuted,
                "observations": observations,
                "unknowns": unknowns,
            },
            "control": {
                "step": int(state.step),
                "recent_failures": failures,
                "recovery_directive": dict(state.recovery_directive) if state.recovery_directive is not None else None,
                "strategy_generation": int(state.strategy_generation),
                "recovery_halted": bool(state.recovery_halted),
                "recovery_halt_reason": state.recovery_halt_reason,
                "progress": state.progress.dump(),
            },
            "tools": self._project_tools(tools),
        })
