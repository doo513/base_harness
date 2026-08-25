from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
import json
import platform
import re
import unicodedata

from harness.core.retrieval import RetrievalSourceItem
from harness.core.storage import (
    IntegrityError,
    atomic_write_json,
    atomic_write_text,
    canonical_hash,
)


class ExperienceTier(str, Enum):
    CANDIDATE = "candidate"
    SUPPORTED = "supported"
    REPRODUCED = "reproduced"
    ROBUST = "robust"
    QUARANTINED = "quarantined"


class ExperienceEventKind(str, Enum):
    SUPPORT = "support"
    SOFT_CONTRADICTION = "soft_contradiction"
    HARD_CONTRADICTION = "hard_contradiction"
    NOT_APPLICABLE = "not_applicable"


class ExperienceRecordingClass(str, Enum):
    VERIFIED_SUCCESS = "verified_success"
    CRITICAL_FAILURE = "critical_failure"
    COUNTEREXAMPLE = "counterexample"


@dataclass(frozen=True)
class ExperienceTrustPolicy:
    reproduced_min_families: int = 2
    robust_min_families: int = 3
    robust_min_environments: int = 2
    soft_contradictions_per_demotion: int = 2
    stale_after_days: int = 180

    def __post_init__(self) -> None:
        values = {
            "reproduced_min_families": self.reproduced_min_families,
            "robust_min_families": self.robust_min_families,
            "robust_min_environments": self.robust_min_environments,
            "soft_contradictions_per_demotion": self.soft_contradictions_per_demotion,
            "stale_after_days": self.stale_after_days,
        }
        for name, value in values.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.robust_min_families < self.reproduced_min_families:
            raise ValueError("robust_min_families cannot be lower than reproduced_min_families")

    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": "experience-trust-policy-v1",
            "reproduced_min_families": self.reproduced_min_families,
            "robust_min_families": self.robust_min_families,
            "robust_min_environments": self.robust_min_environments,
            "soft_contradictions_per_demotion": self.soft_contradictions_per_demotion,
            "stale_after_days": self.stale_after_days,
            "promotion_counts": "independent_evidence_families_only",
            "hard_contradiction_policy": "quarantine",
            "non_use_policy": "no_demotion",
        }


@dataclass(frozen=True)
class ExperienceCandidate:
    key: str
    kind: str
    title: str
    domain: str
    claim: str
    situation: str
    reason: str
    action: str
    result: str
    tags: tuple[str, ...]
    applicability: tuple[tuple[str, str], ...]
    recording_class: ExperienceRecordingClass
    event_kind: ExperienceEventKind
    evidence_refs: tuple[str, ...]
    created_step: int

    def applicability_dict(self) -> dict[str, str]:
        return dict(self.applicability)

    def case_id(self, *, project_id: str) -> str:
        return canonical_hash({
            "schema_version": "experience-case-identity-v1",
            "project_id": project_id,
            "kind": self.kind,
            "domain": self.domain,
            "claim": self.claim,
            "applicability": self.applicability_dict(),
        })


def default_environment_descriptor() -> dict[str, str]:
    return {
        "os": platform.system().lower() or "unknown",
        "os_release": platform.release() or "unknown",
        "machine": platform.machine() or "unknown",
        "python": platform.python_version(),
    }


def _artifact_identity(ref: str) -> str:
    match = re.match(r"^artifact://([0-9a-fA-F]{64})(?:_|$)", ref)
    if match:
        return match.group(1).lower()
    return canonical_hash({"opaque_evidence_ref": ref})


def _slug(value: str, *, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = re.sub(r"[^\w.-]+", "-", normalized, flags=re.UNICODE)
    normalized = normalized.strip("._-")
    return (normalized or fallback)[:96]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntegrityError("experience event recorded_at is invalid") from exc
    if parsed.tzinfo is None:
        raise IntegrityError("experience event recorded_at must include timezone")
    return parsed.astimezone(timezone.utc)


def _string_map(value: Any, *, label: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise IntegrityError(f"{label} must be an object")
    output: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise IntegrityError(f"{label} must contain only string keys and values")
        output[key] = item
    return output


@dataclass(frozen=True)
class ExperienceEvent:
    event_id: str
    case_id: str
    project_id: str
    kind: str
    title: str
    domain: str
    claim: str
    situation: str
    reason: str
    action: str
    result: str
    tags: tuple[str, ...]
    applicability: tuple[tuple[str, str], ...]
    recording_class: ExperienceRecordingClass
    event_kind: ExperienceEventKind
    source_run_id: str
    source_step: int
    evidence_refs: tuple[str, ...]
    evidence_family_id: str
    goal_contract_revision: str
    verifier_id: str
    verifier_revision: str
    environment: tuple[tuple[str, str], ...]
    environment_fingerprint: str
    recorded_at: str

    def body(self) -> dict[str, Any]:
        return {
            "schema_version": "experience-evidence-event-v1",
            "event_id": self.event_id,
            "case_id": self.case_id,
            "project_id": self.project_id,
            "kind": self.kind,
            "title": self.title,
            "domain": self.domain,
            "claim": self.claim,
            "situation": self.situation,
            "reason": self.reason,
            "action": self.action,
            "result": self.result,
            "tags": list(self.tags),
            "applicability": dict(self.applicability),
            "recording_class": self.recording_class.value,
            "event_kind": self.event_kind.value,
            "source_run_id": self.source_run_id,
            "source_step": self.source_step,
            "evidence_refs": list(self.evidence_refs),
            "evidence_family_id": self.evidence_family_id,
            "goal_contract_revision": self.goal_contract_revision,
            "verifier_id": self.verifier_id,
            "verifier_revision": self.verifier_revision,
            "environment": dict(self.environment),
            "environment_fingerprint": self.environment_fingerprint,
            "recorded_at": self.recorded_at,
            "trust": "untrusted_experience_memory",
            "instruction_authority": "none",
            "completion_authority": False,
        }

    def identity(self) -> dict[str, Any]:
        body = self.body()
        body.pop("recorded_at", None)
        return body

    @classmethod
    def load(cls, body: Any) -> "ExperienceEvent":
        if not isinstance(body, dict):
            raise IntegrityError("experience event body is malformed")
        if body.get("schema_version") != "experience-evidence-event-v1":
            raise IntegrityError("unsupported experience event schema")
        if body.get("trust") != "untrusted_experience_memory":
            raise IntegrityError("experience event trust field is invalid")
        if body.get("instruction_authority") != "none" or body.get("completion_authority") is not False:
            raise IntegrityError("experience event authority fields are invalid")
        required_text = (
            "event_id", "case_id", "project_id", "kind", "title", "domain",
            "claim", "situation", "reason", "action", "result", "source_run_id",
            "evidence_family_id", "goal_contract_revision", "verifier_id",
            "verifier_revision", "environment_fingerprint", "recorded_at",
        )
        if any(not isinstance(body.get(name), str) or not body[name] for name in required_text):
            raise IntegrityError("experience event is missing required text fields")
        tags = body.get("tags")
        refs = body.get("evidence_refs")
        if not isinstance(tags, list) or not all(isinstance(item, str) for item in tags):
            raise IntegrityError("experience event tags are malformed")
        if not isinstance(refs, list) or not refs or not all(isinstance(item, str) for item in refs):
            raise IntegrityError("experience event evidence refs are malformed")
        try:
            source_step = int(body.get("source_step"))
            recording_class = ExperienceRecordingClass(body.get("recording_class"))
            event_kind = ExperienceEventKind(body.get("event_kind"))
        except (TypeError, ValueError) as exc:
            raise IntegrityError("experience event enum or numeric fields are malformed") from exc
        if source_step < 0:
            raise IntegrityError("experience event source_step cannot be negative")
        applicability = _string_map(body.get("applicability"), label="experience applicability")
        environment = _string_map(body.get("environment"), label="experience environment")
        _parse_utc(body["recorded_at"])
        return cls(
            event_id=body["event_id"],
            case_id=body["case_id"],
            project_id=body["project_id"],
            kind=body["kind"],
            title=body["title"],
            domain=body["domain"],
            claim=body["claim"],
            situation=body["situation"],
            reason=body["reason"],
            action=body["action"],
            result=body["result"],
            tags=tuple(tags),
            applicability=tuple(sorted(applicability.items())),
            recording_class=recording_class,
            event_kind=event_kind,
            source_run_id=body["source_run_id"],
            source_step=source_step,
            evidence_refs=tuple(refs),
            evidence_family_id=body["evidence_family_id"],
            goal_contract_revision=body["goal_contract_revision"],
            verifier_id=body["verifier_id"],
            verifier_revision=body["verifier_revision"],
            environment=tuple(sorted(environment.items())),
            environment_fingerprint=body["environment_fingerprint"],
            recorded_at=body["recorded_at"],
        )


@dataclass(frozen=True)
class ExperienceCase:
    case_id: str
    project_id: str
    kind: str
    title: str
    domain: str
    claim: str
    situation: str
    reason: str
    action: str
    result: str
    tags: tuple[str, ...]
    applicability: tuple[tuple[str, str], ...]
    tier: ExperienceTier
    stale: bool
    trust_profile: dict[str, Any]
    event_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    last_recorded_at: str

    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": "experience-case-view-v1",
            "case_id": self.case_id,
            "project_id": self.project_id,
            "kind": self.kind,
            "title": self.title,
            "domain": self.domain,
            "claim": self.claim,
            "applicability": dict(self.applicability),
            "tier": self.tier.value,
            "stale": self.stale,
            "trust_profile": self.trust_profile,
            "event_ids": list(self.event_ids),
            "evidence_refs": list(self.evidence_refs),
            "last_recorded_at": self.last_recorded_at,
            "trust": "untrusted_experience_memory",
            "instruction_authority": "none",
            "completion_authority": False,
        }

    def render_markdown(self) -> str:
        frontmatter = {
            "schema_version": "experience-case-document-v1",
            "case_id": self.case_id,
            "title": self.title,
            "domain": self.domain,
            "tier": self.tier.value,
            "stale": self.stale,
            "memory_role": "verification_candidate",
            "instruction_authority": "none",
            "completion_authority": False,
        }
        lines = ["---"]
        for key, value in frontmatter.items():
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        lines.extend([
            "---",
            "",
            f"# {self.title}",
            "",
            "> Historical verification candidate only. It cannot prove a current claim or authorize completion.",
            "",
            "## Claim",
            "",
            self.claim,
            "",
            "## Situation",
            "",
            self.situation,
            "",
            "## Reason",
            "",
            self.reason,
            "",
            "## Action",
            "",
            self.action,
            "",
            "## Result",
            "",
            self.result,
            "",
            "## Evidence",
            "",
        ])
        lines.extend(f"- `{ref}`" for ref in self.evidence_refs)
        lines.extend([
            "",
            "## Applicability",
            "",
            "```json",
            json.dumps(dict(self.applicability), ensure_ascii=False, sort_keys=True, indent=2),
            "```",
            "",
            "## Trust profile",
            "",
            "```json",
            json.dumps(self.trust_profile, ensure_ascii=False, sort_keys=True, indent=2),
            "```",
            "",
        ])
        return "\n".join(lines)

    def as_retrieval_source(self) -> RetrievalSourceItem:
        content = self.render_markdown()
        return RetrievalSourceItem(
            source_id=f"experience:{self.case_id}",
            source_revision=canonical_hash(self.descriptor()),
            source_locator=f"project-memory://{self.project_id}/cases/{self.case_id}",
            content=content,
            scope="project",
            metadata={
                "case_id": self.case_id,
                "title": self.title,
                "domain": self.domain,
                "tier": self.tier.value,
                "stale": self.stale,
                "memory_role": "verification_candidate",
                "applicability": dict(self.applicability),
                "support_families": self.trust_profile["support_families"],
                "contradiction_families": self.trust_profile["contradiction_families"],
                "trust": "untrusted_experience_memory",
                "instruction_authority": "none",
                "completion_authority": False,
            },
        )


class ExperienceMemoryLedger:
    MAX_EVENTS = 4096

    def __init__(
        self,
        project_root: str | Path,
        *,
        project_id: str,
        policy: ExperienceTrustPolicy | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.project_id = project_id
        self.policy = policy or ExperienceTrustPolicy()
        self.events_dir = self.project_root / "experience-events"
        self.documents_dir = self.project_root / "experience-documents"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.documents_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _goal_revision(descriptor: Mapping[str, Any] | None) -> str:
        if descriptor is None:
            return "unspecified-goal-contract"
        return canonical_hash(dict(descriptor))

    @staticmethod
    def _verifier_identity(descriptor: Mapping[str, Any] | None) -> tuple[str, str]:
        if descriptor is None:
            return "unspecified-verifier", "unspecified-verifier-revision"
        copied = dict(descriptor)
        verifier_id = str(copied.get("profile") or copied.get("verifier_id") or "harness-verifier")
        return verifier_id, canonical_hash(copied)

    @staticmethod
    def _evidence_family(refs: tuple[str, ...]) -> str:
        return canonical_hash({
            "schema_version": "evidence-family-v1",
            "content_roots": sorted({_artifact_identity(ref) for ref in refs}),
        })

    def _event_path(self, event_id: str) -> Path:
        return self.events_dir / f"{event_id}.json"

    def append(
        self,
        candidate: ExperienceCandidate,
        *,
        source_run_id: str,
        goal_contract_descriptor: Mapping[str, Any] | None = None,
        verifier_descriptor: Mapping[str, Any] | None = None,
        environment_descriptor: Mapping[str, str] | None = None,
    ) -> tuple[ExperienceEvent, bool]:
        case_id = candidate.case_id(project_id=self.project_id)
        evidence_family_id = self._evidence_family(candidate.evidence_refs)
        environment = dict(environment_descriptor or default_environment_descriptor())
        if not environment or any(not isinstance(k, str) or not isinstance(v, str) for k, v in environment.items()):
            raise ValueError("environment descriptor must contain string keys and values")
        environment_fingerprint = canonical_hash(environment)
        goal_revision = self._goal_revision(goal_contract_descriptor)
        verifier_id, verifier_revision = self._verifier_identity(verifier_descriptor)
        event_id = canonical_hash({
            "schema_version": "experience-event-identity-v1",
            "case_id": case_id,
            "event_kind": candidate.event_kind.value,
            "recording_class": candidate.recording_class.value,
            "source_run_id": source_run_id,
            "source_step": candidate.created_step,
            "evidence_family_id": evidence_family_id,
            "goal_contract_revision": goal_revision,
            "verifier_revision": verifier_revision,
            "environment_fingerprint": environment_fingerprint,
        })
        event = ExperienceEvent(
            event_id=event_id,
            case_id=case_id,
            project_id=self.project_id,
            kind=candidate.kind,
            title=candidate.title,
            domain=candidate.domain,
            claim=candidate.claim,
            situation=candidate.situation,
            reason=candidate.reason,
            action=candidate.action,
            result=candidate.result,
            tags=candidate.tags,
            applicability=candidate.applicability,
            recording_class=candidate.recording_class,
            event_kind=candidate.event_kind,
            source_run_id=source_run_id,
            source_step=candidate.created_step,
            evidence_refs=candidate.evidence_refs,
            evidence_family_id=evidence_family_id,
            goal_contract_revision=goal_revision,
            verifier_id=verifier_id,
            verifier_revision=verifier_revision,
            environment=tuple(sorted(environment.items())),
            environment_fingerprint=environment_fingerprint,
            recorded_at="pending",
        )
        path = self._event_path(event_id)
        if path.exists():
            existing = self._load_event_path(path)
            if existing.identity() != event.identity():
                raise IntegrityError("experience event id collision with different content")
            return existing, False

        event = ExperienceEvent(**{**event.__dict__, "recorded_at": _utc_now()})
        body = event.body()
        atomic_write_json(path, {
            "body": body,
            "integrity": {"algorithm": "sha256", "sha256": canonical_hash(body)},
        })
        return event, True

    def _load_event_path(self, path: Path) -> ExperienceEvent:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrityError(f"experience event cannot be read: {path.name}: {exc}") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("body"), dict):
            raise IntegrityError("experience event envelope is malformed")
        integrity = raw.get("integrity")
        body = raw["body"]
        if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
            raise IntegrityError("experience event integrity metadata is missing")
        if integrity.get("sha256") != canonical_hash(body):
            raise IntegrityError("experience event integrity hash mismatch")
        event = ExperienceEvent.load(body)
        if event.project_id != self.project_id:
            raise IntegrityError("experience event belongs to a different project")
        if path.stem != event.event_id:
            raise IntegrityError("experience event filename/id mismatch")
        return event

    def load_events(self) -> list[ExperienceEvent]:
        paths = sorted(self.events_dir.glob("*.json"))
        if len(paths) > self.MAX_EVENTS:
            raise IntegrityError("experience event count exceeds bound")
        return [self._load_event_path(path) for path in paths]

    def event_count(self) -> int:
        count = len(list(self.events_dir.glob("*.json")))
        if count > self.MAX_EVENTS:
            raise IntegrityError("experience event count exceeds bound")
        return count

    def derive_cases(self, events: list[ExperienceEvent] | None = None) -> list[ExperienceCase]:
        grouped: dict[str, list[ExperienceEvent]] = {}
        for event in self.load_events() if events is None else events:
            grouped.setdefault(event.case_id, []).append(event)

        now = datetime.now(timezone.utc)
        cases: list[ExperienceCase] = []
        rank_tiers = (
            ExperienceTier.CANDIDATE,
            ExperienceTier.SUPPORTED,
            ExperienceTier.REPRODUCED,
            ExperienceTier.ROBUST,
        )
        for case_id, case_events in sorted(grouped.items()):
            case_events.sort(key=lambda item: (item.recorded_at, item.event_id))
            representative = next(
                (item for item in case_events if item.event_kind is ExperienceEventKind.SUPPORT),
                case_events[0],
            )
            support_families = {
                item.evidence_family_id
                for item in case_events
                if item.event_kind is ExperienceEventKind.SUPPORT
            }
            soft_families = {
                item.evidence_family_id
                for item in case_events
                if item.event_kind is ExperienceEventKind.SOFT_CONTRADICTION
            }
            hard_families = {
                item.evidence_family_id
                for item in case_events
                if item.event_kind is ExperienceEventKind.HARD_CONTRADICTION
            }
            not_applicable_families = {
                item.evidence_family_id
                for item in case_events
                if item.event_kind is ExperienceEventKind.NOT_APPLICABLE
            }
            support_events = [
                item for item in case_events if item.event_kind is ExperienceEventKind.SUPPORT
            ]
            environments = {item.environment_fingerprint for item in support_events}
            verifiers = {item.verifier_revision for item in support_events}
            goal_revisions = {item.goal_contract_revision for item in case_events}

            base_rank = 0
            if support_families:
                base_rank = 1
            if len(support_families) >= self.policy.reproduced_min_families:
                base_rank = 2
            if (
                len(support_families) >= self.policy.robust_min_families
                and len(environments) >= self.policy.robust_min_environments
            ):
                base_rank = 3

            demotions = len(soft_families) // self.policy.soft_contradictions_per_demotion
            if hard_families:
                tier = ExperienceTier.QUARANTINED
            else:
                tier = rank_tiers[max(0, base_rank - demotions)]

            last_recorded_at = max(item.recorded_at for item in case_events)
            age_days = max(0, (now - _parse_utc(last_recorded_at)).days)
            stale = age_days >= self.policy.stale_after_days
            trust_profile = {
                "support_families": len(support_families),
                "contradiction_families": len(soft_families) + len(hard_families),
                "soft_contradiction_families": len(soft_families),
                "hard_contradiction_families": len(hard_families),
                "not_applicable_families": len(not_applicable_families),
                "independent_runs": len({item.source_run_id for item in support_events}),
                "environment_fingerprints": len(environments),
                "verifier_revisions": len(verifiers),
                "goal_contract_revisions": len(goal_revisions),
                "age_days": age_days,
                "tier_basis": "derived_from_append_only_events",
                "current_direct_evidence_required": True,
            }
            cases.append(ExperienceCase(
                case_id=case_id,
                project_id=self.project_id,
                kind=representative.kind,
                title=representative.title,
                domain=representative.domain,
                claim=representative.claim,
                situation=representative.situation,
                reason=representative.reason,
                action=representative.action,
                result=representative.result,
                tags=tuple(sorted({tag for item in case_events for tag in item.tags})),
                applicability=representative.applicability,
                tier=tier,
                stale=stale,
                trust_profile=trust_profile,
                event_ids=tuple(item.event_id for item in case_events),
                evidence_refs=tuple(sorted({ref for item in case_events for ref in item.evidence_refs})),
                last_recorded_at=last_recorded_at,
            ))
        return cases

    def materialize_documents(self) -> list[str]:
        written: list[str] = []
        for case in self.derive_cases():
            domain_dir = self.documents_dir / _slug(case.domain, fallback="general")
            filename = f"{_slug(case.title, fallback='case')}--{case.case_id[:12]}.md"
            path = domain_dir / filename
            atomic_write_text(path, case.render_markdown())
            written.append(str(path))
        return written

    def retrieval_sources(self) -> list[RetrievalSourceItem]:
        return [case.as_retrieval_source() for case in self.derive_cases()]

    def descriptor(self) -> dict[str, Any]:
        events = self.load_events()
        cases = self.derive_cases(events)
        return {
            "schema_version": "experience-memory-ledger-v1",
            "event_count": len(events),
            "case_count": len(cases),
            "events_hash": canonical_hash([event.body() for event in events]),
            "cases_hash": canonical_hash([case.descriptor() for case in cases]),
            "policy": self.policy.descriptor(),
            "source_of_truth": "append_only_evidence_events",
            "document_projection": "title_based_markdown",
            "rag_projection": "untrusted_verification_candidates",
            "trust": "untrusted_experience_memory",
            "instruction_authority": "none",
            "completion_authority": False,
        }
