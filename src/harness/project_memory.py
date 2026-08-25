from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
import json
import re

from harness.core.retrieval import LocalLexicalRetrievalGateway, RetrievalSourceItem
from harness.core.storage import IntegrityError, atomic_write_json, canonical_hash
from harness.experience_memory import (
    ExperienceCandidate,
    ExperienceEventKind,
    ExperienceMemoryLedger,
    ExperienceRecordingClass,
    ExperienceTrustPolicy,
)


_MEMORY_KEY_PREFIX = "memory_candidate."
_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_DOMAIN_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class ProjectMemoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class MemoryCandidate:
    key: str
    kind: str
    content: str
    tags: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    created_step: int


@dataclass(frozen=True)
class ProjectMemoryRecord:
    record_id: str
    project_id: str
    kind: str
    content: str
    tags: tuple[str, ...]
    source_run_id: str
    source_step: int
    evidence_refs: tuple[str, ...]

    def body(self) -> dict[str, Any]:
        return {
            "schema_version": "project-memory-record-v1",
            "record_id": self.record_id,
            "project_id": self.project_id,
            "kind": self.kind,
            "content": self.content,
            "tags": list(self.tags),
            "source_run_id": self.source_run_id,
            "source_step": int(self.source_step),
            "evidence_refs": list(self.evidence_refs),
            "trust": "untrusted_project_memory",
            "instruction_authority": "none",
        }

    def as_retrieval_source(self) -> RetrievalSourceItem:
        content_hash = canonical_hash({"content": self.content})
        return RetrievalSourceItem(
            source_id=f"memory:{content_hash}",
            source_revision=self.record_id,
            source_locator=f"project-memory://{self.project_id}/{self.record_id}",
            content=self.content,
            scope="project",
            metadata={
                "memory_kind": self.kind,
                "project_id": self.project_id,
                "source_run_id": self.source_run_id,
                "source_step": self.source_step,
                "tags": list(self.tags),
                "trust": "untrusted_project_memory",
            },
        )


class ProjectMemoryRetrievalGateway(LocalLexicalRetrievalGateway):
    provider_id = "project_memory"
    provider_revision = "project-memory-v2"


class ProjectMemoryStore:
    """Cross-run untrusted project/episodic memory store.

    Writes happen after a run returns. A running/resumable run therefore uses a
    frozen snapshot of memory and never observes its own staged writes. Memory
    can assist later runs only through the Stage-08 retrieval admission path.
    """

    MAX_RECORDS = 4096
    MAX_CONTENT_CHARS = 4000
    MAX_TAGS = 16
    MAX_TAG_CHARS = 128
    MAX_TITLE_CHARS = 200
    MAX_DOMAIN_CHARS = 128
    MAX_CASE_FIELD_CHARS = 4000
    MAX_CASE_TOTAL_CHARS = 16_000
    MAX_APPLICABILITY_ITEMS = 16
    MAX_APPLICABILITY_KEY_CHARS = 128
    MAX_APPLICABILITY_VALUE_CHARS = 500

    def __init__(
        self,
        root: str | Path,
        *,
        project_id: str,
        workspace_root: str | Path,
        trust_policy: ExperienceTrustPolicy | None = None,
    ):
        self.root = Path(root).expanduser().resolve()
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        if not _PROJECT_ID_RE.fullmatch(project_id):
            raise ProjectMemoryError("project_id must match [A-Za-z0-9_.-]{1,128}")
        self.project_id = project_id
        if self._overlap(self.root, self.workspace_root):
            raise ProjectMemoryError("project memory root and actor workspace must not overlap")
        self.project_root = self.root / self.project_id
        self.items_dir = self.project_root / "items"
        self.items_dir.mkdir(parents=True, exist_ok=True)
        self.experience_ledger = ExperienceMemoryLedger(
            self.project_root,
            project_id=self.project_id,
            policy=trust_policy,
        )

    @staticmethod
    def _contains(parent: Path, child: Path) -> bool:
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False

    @classmethod
    def _overlap(cls, a: Path, b: Path) -> bool:
        return a == b or cls._contains(a, b) or cls._contains(b, a)

    @staticmethod
    def default_project_id(workspace_root: str | Path) -> str:
        resolved = str(Path(workspace_root).expanduser().resolve())
        return "workspace-" + canonical_hash({"workspace": resolved})[:24]

    @classmethod
    def _validate_candidate_value(cls, key: str, value: Any, evidence_refs: Iterable[str], *, step: int) -> MemoryCandidate:
        if not key.startswith(_MEMORY_KEY_PREFIX):
            raise ProjectMemoryError("memory candidate key has invalid prefix")
        if not isinstance(value, dict) or set(value) - {"kind", "content", "tags"}:
            raise ProjectMemoryError("memory candidate value must contain only kind/content/tags")
        kind = value.get("kind")
        content = value.get("content")
        tags = value.get("tags", [])
        if kind not in {"project", "episodic"}:
            raise ProjectMemoryError("memory candidate kind must be project or episodic")
        if not isinstance(content, str) or not content.strip():
            raise ProjectMemoryError("memory candidate content must be a non-empty string")
        content = content.strip()
        if len(content) > cls.MAX_CONTENT_CHARS:
            raise ProjectMemoryError("memory candidate content exceeds bound")
        if not isinstance(tags, list) or len(tags) > cls.MAX_TAGS:
            raise ProjectMemoryError("memory candidate tags exceed bound")
        normalized_tags: list[str] = []
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip() or len(tag.strip()) > cls.MAX_TAG_CHARS:
                raise ProjectMemoryError("memory candidate tag is invalid")
            normalized_tags.append(tag.strip())
        if len(normalized_tags) != len(set(normalized_tags)):
            raise ProjectMemoryError("memory candidate tags must be unique")
        refs = tuple(str(ref) for ref in evidence_refs)
        if not refs:
            raise ProjectMemoryError("memory candidate requires at least one run evidence reference")
        if len(refs) != len(set(refs)):
            raise ProjectMemoryError("memory candidate evidence refs must be unique")
        return MemoryCandidate(
            key=key,
            kind=kind,
            content=content,
            tags=tuple(sorted(normalized_tags)),
            evidence_refs=refs,
            created_step=int(step),
        )

    @staticmethod
    def _bounded_text(
        value: Any,
        *,
        label: str,
        max_chars: int,
        single_line: bool = False,
    ) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ProjectMemoryError(f"{label} must be a non-empty string")
        normalized = value.strip()
        if len(normalized) > max_chars:
            raise ProjectMemoryError(f"{label} exceeds bound")
        if single_line and any(char in normalized for char in "\r\n"):
            raise ProjectMemoryError(f"{label} must be a single line")
        return normalized

    @classmethod
    def _validate_experience_candidate_value(
        cls,
        key: str,
        value: Any,
        evidence_refs: Iterable[str],
        *,
        step: int,
    ) -> ExperienceCandidate:
        allowed = {
            "schema_version", "kind", "title", "domain", "claim", "situation",
            "reason", "action", "result", "tags", "applicability",
            "recording_class", "event_kind",
        }
        if not key.startswith(_MEMORY_KEY_PREFIX):
            raise ProjectMemoryError("memory candidate key has invalid prefix")
        if not isinstance(value, dict) or set(value) - allowed:
            raise ProjectMemoryError("experience candidate contains unsupported fields")
        if value.get("schema_version") != "experience-case-candidate-v2":
            raise ProjectMemoryError("unsupported experience candidate schema")
        kind = value.get("kind")
        if kind not in {"project", "episodic"}:
            raise ProjectMemoryError("experience candidate kind must be project or episodic")
        title = cls._bounded_text(
            value.get("title"), label="experience title", max_chars=cls.MAX_TITLE_CHARS, single_line=True
        )
        domain = cls._bounded_text(
            value.get("domain"), label="experience domain", max_chars=cls.MAX_DOMAIN_CHARS, single_line=True
        )
        if not _DOMAIN_RE.fullmatch(domain):
            raise ProjectMemoryError("experience domain must match [A-Za-z0-9_.-]{1,128}")
        fields = {
            name: cls._bounded_text(
                value.get(name), label=f"experience {name}", max_chars=cls.MAX_CASE_FIELD_CHARS
            )
            for name in ("claim", "situation", "reason", "action", "result")
        }
        if len(title) + len(domain) + sum(len(item) for item in fields.values()) > cls.MAX_CASE_TOTAL_CHARS:
            raise ProjectMemoryError("experience candidate total text exceeds bound")

        tags = value.get("tags", [])
        if not isinstance(tags, list) or len(tags) > cls.MAX_TAGS:
            raise ProjectMemoryError("experience candidate tags exceed bound")
        normalized_tags: list[str] = []
        for tag in tags:
            normalized = cls._bounded_text(
                tag, label="experience tag", max_chars=cls.MAX_TAG_CHARS, single_line=True
            )
            normalized_tags.append(normalized)
        if len(normalized_tags) != len(set(normalized_tags)):
            raise ProjectMemoryError("experience candidate tags must be unique")

        applicability = value.get("applicability")
        if not isinstance(applicability, dict) or len(applicability) > cls.MAX_APPLICABILITY_ITEMS:
            raise ProjectMemoryError("experience applicability must be a bounded object")
        normalized_applicability: dict[str, str] = {}
        for raw_key, raw_value in applicability.items():
            key_text = cls._bounded_text(
                raw_key,
                label="applicability key",
                max_chars=cls.MAX_APPLICABILITY_KEY_CHARS,
                single_line=True,
            )
            value_text = cls._bounded_text(
                raw_value,
                label=f"applicability.{key_text}",
                max_chars=cls.MAX_APPLICABILITY_VALUE_CHARS,
                single_line=True,
            )
            normalized_applicability[key_text] = value_text
        try:
            recording_class = ExperienceRecordingClass(value.get("recording_class"))
            event_kind = ExperienceEventKind(value.get("event_kind"))
        except ValueError as exc:
            raise ProjectMemoryError("experience recording_class or event_kind is invalid") from exc
        if recording_class in {
            ExperienceRecordingClass.VERIFIED_SUCCESS,
            ExperienceRecordingClass.CRITICAL_FAILURE,
        } and event_kind is not ExperienceEventKind.SUPPORT:
            raise ProjectMemoryError("success/failure cases must support their recorded claim")
        if recording_class is ExperienceRecordingClass.COUNTEREXAMPLE and event_kind is ExperienceEventKind.SUPPORT:
            raise ProjectMemoryError("counterexample must contradict or mark a case not applicable")

        refs = tuple(str(ref) for ref in evidence_refs)
        if not refs:
            raise ProjectMemoryError("experience candidate requires at least one run evidence reference")
        if len(refs) != len(set(refs)):
            raise ProjectMemoryError("experience candidate evidence refs must be unique")
        return ExperienceCandidate(
            key=key,
            kind=kind,
            title=title,
            domain=domain,
            claim=fields["claim"],
            situation=fields["situation"],
            reason=fields["reason"],
            action=fields["action"],
            result=fields["result"],
            tags=tuple(sorted(normalized_tags)),
            applicability=tuple(sorted(normalized_applicability.items())),
            recording_class=recording_class,
            event_kind=event_kind,
            evidence_refs=refs,
            created_step=int(step),
        )

    @staticmethod
    def _validate_experience_eligibility(candidate: ExperienceCandidate, state) -> None:
        if candidate.recording_class is ExperienceRecordingClass.VERIFIED_SUCCESS:
            if not state.completed:
                raise ProjectMemoryError("verified_success memory requires accepted run completion")
        elif candidate.recording_class is ExperienceRecordingClass.CRITICAL_FAILURE:
            if not state.failures:
                raise ProjectMemoryError("critical_failure memory requires a recorded run failure")
        elif candidate.event_kind in {
            ExperienceEventKind.SOFT_CONTRADICTION,
            ExperienceEventKind.HARD_CONTRADICTION,
        }:
            if not state.refuted_hypotheses and not state.failures:
                raise ProjectMemoryError("contradiction memory requires a refutation or recorded failure")

    def candidates_from_state(
        self,
        state,
    ) -> tuple[list[MemoryCandidate | ExperienceCandidate], list[dict[str, str]]]:
        accepted: list[MemoryCandidate | ExperienceCandidate] = []
        rejected: list[dict[str, str]] = []
        registered = set(state.evidence_refs) & set(state.artifacts)
        for key, claim in sorted(state.hypotheses.items()):
            if not key.startswith(_MEMORY_KEY_PREFIX):
                continue
            try:
                if (
                    isinstance(claim.value, dict)
                    and claim.value.get("schema_version") == "experience-case-candidate-v2"
                ):
                    candidate = self._validate_experience_candidate_value(
                        key, claim.value, claim.evidence_refs, step=state.step
                    )
                    self._validate_experience_eligibility(candidate, state)
                else:
                    candidate = self._validate_candidate_value(
                        key, claim.value, claim.evidence_refs, step=state.step
                    )
                missing = [ref for ref in candidate.evidence_refs if ref not in registered]
                if missing:
                    raise ProjectMemoryError("memory candidate references unregistered evidence")
            except ProjectMemoryError as exc:
                rejected.append({"key": key, "reason": str(exc)})
                continue
            accepted.append(candidate)
        return accepted, rejected

    @staticmethod
    def _record_id(candidate: MemoryCandidate, *, project_id: str, source_run_id: str) -> str:
        return canonical_hash({
            "project_id": project_id,
            "kind": candidate.kind,
            "content": candidate.content,
            "tags": list(candidate.tags),
            "source_run_id": source_run_id,
            "source_step": candidate.created_step,
            "evidence_refs": list(candidate.evidence_refs),
        })

    @staticmethod
    def _goal_contract_descriptor(goal_contract: Any | None) -> dict[str, Any] | None:
        if goal_contract is None:
            return None
        return {
            "schema_version": "goal-contract-memory-binding-v1",
            "goal": goal_contract.goal,
            "acceptance": list(goal_contract.acceptance),
            "constraints": list(goal_contract.constraints),
            "pinned_constraints": list(goal_contract.pinned_constraints),
            "task_id": goal_contract.task_id,
        }

    def publish_from_state(
        self,
        state,
        *,
        source_run_id: str,
        goal_contract: Any | None = None,
        verifier_descriptor: Mapping[str, Any] | None = None,
        environment_descriptor: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(source_run_id, str) or not source_run_id:
            raise ProjectMemoryError("source_run_id must be a non-empty string")
        candidates, rejected = self.candidates_from_state(state)
        existing_count = len(list(self.items_dir.glob("*.json"))) + self.experience_ledger.event_count()
        if existing_count + len(candidates) > self.MAX_RECORDS:
            raise ProjectMemoryError("project memory record capacity exceeded")

        published: list[str] = []
        deduplicated: list[str] = []
        experience_touched = False
        for candidate in candidates:
            if isinstance(candidate, ExperienceCandidate):
                event, created = self.experience_ledger.append(
                    candidate,
                    source_run_id=source_run_id,
                    goal_contract_descriptor=self._goal_contract_descriptor(goal_contract),
                    verifier_descriptor=verifier_descriptor,
                    environment_descriptor=environment_descriptor,
                )
                (published if created else deduplicated).append(event.event_id)
                experience_touched = True
                continue
            record_id = self._record_id(candidate, project_id=self.project_id, source_run_id=source_run_id)
            record = ProjectMemoryRecord(
                record_id=record_id,
                project_id=self.project_id,
                kind=candidate.kind,
                content=candidate.content,
                tags=candidate.tags,
                source_run_id=source_run_id,
                source_step=candidate.created_step,
                evidence_refs=candidate.evidence_refs,
            )
            body = record.body()
            envelope = {
                "body": body,
                "integrity": {"algorithm": "sha256", "sha256": canonical_hash(body)},
            }
            path = self.items_dir / f"{record_id}.json"
            if path.exists():
                existing = self._load_path(path)
                if existing.body() != body:
                    raise IntegrityError("project memory record id collision with different content")
                deduplicated.append(record_id)
                continue
            atomic_write_json(path, envelope)
            published.append(record_id)
        if experience_touched:
            self.experience_ledger.materialize_documents()
        return {"published": published, "deduplicated": deduplicated, "rejected": rejected}

    def _load_path(self, path: Path) -> ProjectMemoryRecord:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrityError(f"project memory record cannot be read: {path.name}: {exc}") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("body"), dict):
            raise IntegrityError("project memory envelope is malformed")
        integrity = raw.get("integrity")
        body = raw["body"]
        if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
            raise IntegrityError("project memory integrity metadata is missing")
        if integrity.get("sha256") != canonical_hash(body):
            raise IntegrityError("project memory integrity hash mismatch")
        if body.get("schema_version") != "project-memory-record-v1":
            raise IntegrityError("unsupported project memory record schema")
        if body.get("trust") != "untrusted_project_memory" or body.get("instruction_authority") != "none":
            raise IntegrityError("project memory trust fields are invalid")
        record_id = str(body.get("record_id", ""))
        if path.stem != record_id:
            raise IntegrityError("project memory filename/id mismatch")
        if body.get("project_id") != self.project_id:
            raise IntegrityError("project memory record belongs to a different project")
        content = body.get("content")
        tags = body.get("tags", [])
        refs = body.get("evidence_refs", [])
        if not isinstance(content, str) or len(content) > self.MAX_CONTENT_CHARS:
            raise IntegrityError("project memory content is invalid")
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise IntegrityError("project memory tags are invalid")
        if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
            raise IntegrityError("project memory evidence refs are invalid")
        return ProjectMemoryRecord(
            record_id=record_id,
            project_id=self.project_id,
            kind=str(body.get("kind", "")),
            content=content,
            tags=tuple(tags),
            source_run_id=str(body.get("source_run_id", "")),
            source_step=int(body.get("source_step", 0)),
            evidence_refs=tuple(refs),
        )

    def load_records(self) -> list[ProjectMemoryRecord]:
        paths = sorted(self.items_dir.glob("*.json"))
        if len(paths) > self.MAX_RECORDS:
            raise IntegrityError("project memory record count exceeds bound")
        return [self._load_path(path) for path in paths]

    def load_experience_cases(self):
        return self.experience_ledger.derive_cases()

    def snapshot_gateway(self) -> ProjectMemoryRetrievalGateway:
        records = self.load_records()
        cases = self.load_experience_cases()
        items = [record.as_retrieval_source() for record in records]
        items.extend(case.as_retrieval_source() for case in cases)
        index_revision = "project-memory-snapshot:" + canonical_hash(
            {
                "legacy": [record.body() for record in records],
                "experience": [case.descriptor() for case in cases],
            }
        )
        return ProjectMemoryRetrievalGateway(items, index_revision=index_revision)

    def descriptor(self) -> dict[str, Any]:
        records = self.load_records()
        experience = self.experience_ledger.descriptor()
        return {
            "schema_version": "project-memory-store-v2",
            "root": str(self.root),
            "project_id": self.project_id,
            "record_count": len(records) + int(experience["case_count"]),
            "legacy_record_count": len(records),
            "records_hash": canonical_hash([record.body() for record in records]),
            "experience": experience,
            "trust": "untrusted_project_memory",
            "instruction_authority": "none",
            "write_timing": "post_run_publish",
            "read_timing": "frozen_run_start_snapshot",
        }
