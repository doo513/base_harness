from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

from .storage import canonical_json


_TOKEN_RE = re.compile(r"[\w./:-]+", re.UNICODE)


def _tokens(value: Any, *, max_tokens: int = 256, max_token_chars: int = 96) -> list[str]:
    try:
        text = value if isinstance(value, str) else canonical_json(value)
    except Exception:
        text = str(value)
    result: list[str] = []
    for match in _TOKEN_RE.finditer(text.casefold()):
        token = match.group(0)[:max_token_chars]
        if len(token) < 2:
            continue
        result.append(token)
        if len(result) >= max_tokens:
            break
    return result


def _preview(value: Any, limit: int) -> dict[str, Any]:
    try:
        raw = value if isinstance(value, str) else canonical_json(value)
    except Exception:
        raw = str(value)
    visible = raw[:limit]
    return {
        "text": visible,
        "truncated": len(raw) > len(visible),
        "original_chars": len(raw),
        "visible_chars": len(visible),
    }


@dataclass(frozen=True)
class ActiveContextPolicy:
    max_facts: int = 12
    max_hypotheses: int = 8
    max_observations: int = 8
    max_value_preview_chars: int = 800
    max_observation_preview_chars: int = 800
    max_query_tokens: int = 256

    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": "active-context-policy-v1",
            "max_facts": self.max_facts,
            "max_hypotheses": self.max_hypotheses,
            "max_observations": self.max_observations,
            "max_value_preview_chars": self.max_value_preview_chars,
            "max_observation_preview_chars": self.max_observation_preview_chars,
            "max_query_tokens": self.max_query_tokens,
            "ranking": "deterministic_lexical_overlap_active_task_weighted",
            "truth_authority": "none",
            "progress_authority": False,
        }


class ActiveContextProjector:
    """Small deterministic relevance view over durable state.

    This projector only changes visibility priority. It does not change trust,
    claim status, authority, progress, or completion state. The Stage-07 base
    projection remains the authoritative bounded context contract.
    """

    def __init__(self, policy: ActiveContextPolicy | None = None):
        self.policy = policy or ActiveContextPolicy()

    def _query_weights(self, goal, state) -> dict[str, int]:
        weights: dict[str, int] = {}

        def add(value: Any, weight: int) -> None:
            remaining = max(0, self.policy.max_query_tokens - len(weights))
            if remaining == 0:
                return
            for token in _tokens(value, max_tokens=remaining):
                weights[token] = max(weights.get(token, 0), weight)

        add(getattr(goal, "goal", ""), 2)
        add(getattr(goal, "acceptance", []), 1)
        add(getattr(goal, "constraints", []), 1)
        workflow = state.agent_control
        add(workflow.objective or "", 2)
        if workflow.active_task_id is not None:
            task = workflow.tasks.get(workflow.active_task_id)
            if task is not None:
                add(task.title, 4)
                add(task.note or "", 3)
        return weights

    @staticmethod
    def _authority_rank(authority: str) -> int:
        return {
            "external_oracle": 0,
            "environment": 1,
            "trusted_tool": 2,
            "supported": 3,
            "user": 4,
            "observed": 5,
            "model": 6,
            "untrusted_tool": 7,
        }.get(authority, 8)

    @staticmethod
    def _score(value: Any, weights: dict[str, int]) -> int:
        candidate = set(_tokens(value))
        return sum(weight for token, weight in weights.items() if token in candidate)

    def project(self, *, goal, state) -> dict[str, Any]:
        weights = self._query_weights(goal, state)
        if not weights:
            return {
                "schema_version": "active-context-v1",
                "selection_authority": "kernel_deterministic_lexical",
                "truth_authority": "none",
                "progress_authority": False,
                "query_tokens": [],
                "facts": [],
                "hypotheses": [],
                "observations": [],
            }

        fact_candidates: list[tuple[int, int, str, Any]] = []
        for key, claim in state.facts.items():
            if claim.superseded_by is not None:
                continue
            score = self._score({"key": key, "value": claim.value}, weights)
            if score > 0:
                fact_candidates.append((score, self._authority_rank(claim.authority.value), key, claim))
        fact_candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

        hypothesis_candidates: list[tuple[int, str, Any]] = []
        for key, claim in state.hypotheses.items():
            score = self._score({"key": key, "value": claim.value}, weights)
            if score > 0:
                hypothesis_candidates.append((score, key, claim))
        hypothesis_candidates.sort(key=lambda item: (-item[0], item[1]))

        observation_candidates: list[tuple[int, int, int, Any]] = []
        for index, observation in enumerate(state.observations):
            score = self._score(
                {"source": observation.source, "preview": observation.preview, "error": observation.error},
                weights,
            )
            if score > 0:
                observation_candidates.append((score, int(observation.step), index, observation))
        observation_candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))

        facts = [
            {
                "key": key,
                "relevance_score": score,
                "trust": "verified_fact",
                "instruction_authority": "none",
                "authority": claim.authority.value,
                "value_preview": _preview(claim.value, self.policy.max_value_preview_chars),
                "evidence_refs": list(claim.evidence_refs[:8]),
            }
            for score, _, key, claim in fact_candidates[: self.policy.max_facts]
        ]
        hypotheses = [
            {
                "key": key,
                "relevance_score": score,
                "trust": "untrusted_speculation",
                "instruction_authority": "none",
                "value_preview": _preview(claim.value, self.policy.max_value_preview_chars),
                "evidence_refs": list(claim.evidence_refs[:8]),
            }
            for score, key, claim in hypothesis_candidates[: self.policy.max_hypotheses]
        ]
        observations = [
            {
                "source": observation.source,
                "step": int(observation.step),
                "relevance_score": score,
                "trust": "untrusted_observation",
                "instruction_authority": "none",
                "artifact_ref": observation.artifact_ref,
                "preview": _preview(observation.preview, self.policy.max_observation_preview_chars),
            }
            for score, _, _, observation in observation_candidates[: self.policy.max_observations]
        ]

        return {
            "schema_version": "active-context-v1",
            "selection_authority": "kernel_deterministic_lexical",
            "truth_authority": "none",
            "progress_authority": False,
            "policy": self.policy.descriptor(),
            "query_tokens": sorted(weights),
            "facts": facts,
            "hypotheses": hypotheses,
            "observations": observations,
            "omitted": {
                "facts": max(0, len(fact_candidates) - len(facts)),
                "hypotheses": max(0, len(hypothesis_candidates) - len(hypotheses)),
                "observations": max(0, len(observation_candidates) - len(observations)),
            },
        }
