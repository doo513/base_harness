from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol
import hashlib
import re

from .storage import ArtifactStore, IntegrityError, canonical_hash, canonical_json


def normalize_retrieval_query(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("retrieval query must be a string")
    return re.sub(r"\s+", " ", value.strip())


def retrieval_item_id(
    *,
    provider_id: str,
    provider_revision: str,
    source_id: str,
    source_revision: str,
    source_locator: str,
    content_sha256: str,
) -> str:
    return canonical_hash({
        "provider_id": provider_id,
        "provider_revision": provider_revision,
        "source_id": source_id,
        "source_revision": source_revision,
        "source_locator": source_locator,
        "content_sha256": content_sha256,
    })


class RetrievalUnavailable(RuntimeError):
    pass


class RetrievalContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetrievalPolicy:
    enabled: bool = False
    default_scope: str = "project"
    default_top_k: int = 5
    max_query_chars: int = 1000
    max_admitted_per_request: int = 5
    max_context_items: int = 5
    max_preview_chars_per_item: int = 800
    max_total_context_preview_chars: int = 3000
    max_metadata_items: int = 16
    max_metadata_key_chars: int = 128
    max_metadata_value_chars: int = 500

    schema_version = "retrieval-policy-v1"
    ranking_policy_version = "score-desc_source-id_content-sha_item-id-v1"

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be boolean")
        if not isinstance(self.default_scope, str) or not self.default_scope.strip():
            raise ValueError("default_scope must be a non-empty string")
        integer_fields = (
            "default_top_k",
            "max_query_chars",
            "max_admitted_per_request",
            "max_context_items",
            "max_preview_chars_per_item",
            "max_total_context_preview_chars",
            "max_metadata_items",
            "max_metadata_key_chars",
            "max_metadata_value_chars",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.enabled and self.default_top_k < 1:
            raise ValueError("enabled retrieval requires default_top_k >= 1")
        if self.default_top_k > self.max_admitted_per_request:
            raise ValueError("default_top_k cannot exceed max_admitted_per_request")
        if self.max_context_items > self.max_admitted_per_request:
            raise ValueError("max_context_items cannot exceed max_admitted_per_request")

    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "enabled": self.enabled,
            "default_scope": self.default_scope,
            "default_top_k": self.default_top_k,
            "max_query_chars": self.max_query_chars,
            "max_admitted_per_request": self.max_admitted_per_request,
            "max_context_items": self.max_context_items,
            "max_preview_chars_per_item": self.max_preview_chars_per_item,
            "max_total_context_preview_chars": self.max_total_context_preview_chars,
            "max_metadata_items": self.max_metadata_items,
            "max_metadata_key_chars": self.max_metadata_key_chars,
            "max_metadata_value_chars": self.max_metadata_value_chars,
            "ranking_policy_version": self.ranking_policy_version,
            "query_owner": "kernel_descriptor_from_explicit_actor_request",
            "actor_controlled_fields": ["query"],
            "kernel_controlled_fields": ["scope", "top_k", "provider", "ranking", "admission"],
            "trust": "untrusted_retrieval",
            "instruction_authority": "none",
            "retrieval_counts_as_progress": False,
        }

    def sanitize_metadata(self, metadata: Any) -> dict[str, str]:
        if not isinstance(metadata, dict):
            return {}
        output: dict[str, str] = {}
        for raw_key in sorted(metadata, key=lambda item: str(item))[: self.max_metadata_items]:
            key = str(raw_key)
            if len(key) > self.max_metadata_key_chars:
                key = f"meta:{canonical_hash({'key': key})[:24]}"
            value = metadata[raw_key]
            if isinstance(value, str):
                rendered = value
            else:
                rendered = canonical_json(value)
            output[key] = rendered[: self.max_metadata_value_chars]
        return output


@dataclass(frozen=True)
class RetrievalSourceItem:
    source_id: str
    source_revision: str
    source_locator: str
    content: str
    scope: str = "project"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("source_id", "source_revision", "source_locator", "scope"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.content, str):
            raise ValueError("content must be a string")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be an object")

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def descriptor(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_revision": self.source_revision,
            "source_locator": self.source_locator,
            "scope": self.scope,
            "content_sha256": self.content_sha256,
            "metadata_hash": canonical_hash(self.metadata),
        }


@dataclass(frozen=True)
class RetrievalRequest:
    request_id: str
    query: str
    normalized_query: str
    scope: str
    top_k: int
    requested_step: int
    strategy_generation: int

    def dump(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "query": self.query,
            "normalized_query": self.normalized_query,
            "scope": self.scope,
            "top_k": int(self.top_k),
            "requested_step": int(self.requested_step),
            "strategy_generation": int(self.strategy_generation),
        }

    @classmethod
    def load(cls, raw: Any) -> "RetrievalRequest":
        if not isinstance(raw, dict):
            raise IntegrityError("retrieval request snapshot is malformed")
        obj = cls(
            request_id=str(raw.get("request_id", "")),
            query=str(raw.get("query", "")),
            normalized_query=str(raw.get("normalized_query", "")),
            scope=str(raw.get("scope", "")),
            top_k=int(raw.get("top_k", 0)),
            requested_step=int(raw.get("requested_step", 0)),
            strategy_generation=int(raw.get("strategy_generation", 0)),
        )
        if not obj.request_id or not obj.normalized_query or not obj.scope or obj.top_k < 1:
            raise IntegrityError("retrieval request snapshot has invalid required fields")
        if normalize_retrieval_query(obj.query) != obj.normalized_query:
            raise IntegrityError("retrieval request normalized query mismatch")
        return obj


@dataclass(frozen=True)
class RetrievalCandidate:
    candidate_id: str
    source_id: str
    source_revision: str
    source_locator: str
    scope: str
    content: str
    content_sha256: str
    score: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.score, int) or isinstance(self.score, bool):
            raise ValueError("retrieval candidate score must be an integer")
        if hashlib.sha256(self.content.encode("utf-8")).hexdigest() != self.content_sha256:
            raise ValueError("retrieval candidate content digest mismatch")
        if not isinstance(self.metadata, dict):
            raise ValueError("retrieval candidate metadata must be an object")


@dataclass
class RetrievalItem:
    item_id: str
    content_ref: str
    content_sha256: str
    source_id: str
    source_revision: str
    source_locator: str
    admitted_step: int
    provider_id: str
    provider_revision: str
    preview: str
    preview_truncated: bool
    content_chars: int
    trust: str = "untrusted_retrieval"
    instruction_authority: str = "none"
    superseded_by: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def dump(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "content_ref": self.content_ref,
            "content_sha256": self.content_sha256,
            "source_id": self.source_id,
            "source_revision": self.source_revision,
            "source_locator": self.source_locator,
            "admitted_step": int(self.admitted_step),
            "provider_id": self.provider_id,
            "provider_revision": self.provider_revision,
            "preview": self.preview,
            "preview_truncated": bool(self.preview_truncated),
            "content_chars": int(self.content_chars),
            "trust": self.trust,
            "instruction_authority": self.instruction_authority,
            "superseded_by": self.superseded_by,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def load(cls, raw: Any) -> "RetrievalItem":
        if not isinstance(raw, dict):
            raise IntegrityError("retrieval item snapshot is malformed")
        if raw.get("trust") != "untrusted_retrieval":
            raise IntegrityError("retrieval item trust field is not fixed untrusted")
        if raw.get("instruction_authority") != "none":
            raise IntegrityError("retrieval item instruction authority is not none")
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, dict):
            raise IntegrityError("retrieval item metadata is malformed")
        item = cls(
            item_id=str(raw.get("item_id", "")),
            content_ref=str(raw.get("content_ref", "")),
            content_sha256=str(raw.get("content_sha256", "")),
            source_id=str(raw.get("source_id", "")),
            source_revision=str(raw.get("source_revision", "")),
            source_locator=str(raw.get("source_locator", "")),
            admitted_step=int(raw.get("admitted_step", 0)),
            provider_id=str(raw.get("provider_id", "")),
            provider_revision=str(raw.get("provider_revision", "")),
            preview=str(raw.get("preview", "")),
            preview_truncated=bool(raw.get("preview_truncated", False)),
            content_chars=int(raw.get("content_chars", 0)),
            trust="untrusted_retrieval",
            instruction_authority="none",
            superseded_by=(
                str(raw["superseded_by"]) if raw.get("superseded_by") is not None else None
            ),
            metadata={str(k): str(v) for k, v in metadata.items()},
        )
        required = (
            item.item_id,
            item.content_ref,
            item.content_sha256,
            item.source_id,
            item.source_revision,
            item.source_locator,
            item.provider_id,
            item.provider_revision,
        )
        if not all(required):
            raise IntegrityError("retrieval item snapshot is missing required fields")
        try:
            ref_digest = ArtifactStore.digest_from_ref(item.content_ref)
        except (ValueError, IntegrityError) as exc:
            raise IntegrityError(f"retrieval item artifact ref is invalid: {exc}") from exc
        if ref_digest != item.content_sha256:
            raise IntegrityError("retrieval item artifact ref digest mismatch")
        expected_id = retrieval_item_id(
            provider_id=item.provider_id,
            provider_revision=item.provider_revision,
            source_id=item.source_id,
            source_revision=item.source_revision,
            source_locator=item.source_locator,
            content_sha256=item.content_sha256,
        )
        if expected_id != item.item_id:
            raise IntegrityError("retrieval item id does not match immutable identity")
        return item


@dataclass(frozen=True)
class RetrievalResultSnapshot:
    request: RetrievalRequest
    item_ids: list[str]

    def dump(self) -> dict[str, Any]:
        return {
            "request": self.request.dump(),
            "item_ids": list(self.item_ids),
        }

    @classmethod
    def load(cls, raw: Any) -> "RetrievalResultSnapshot":
        if not isinstance(raw, dict):
            raise IntegrityError("retrieval result snapshot is malformed")
        item_ids = raw.get("item_ids", [])
        if not isinstance(item_ids, list) or not all(isinstance(x, str) for x in item_ids):
            raise IntegrityError("retrieval result item ids are malformed")
        if len(item_ids) != len(set(item_ids)):
            raise IntegrityError("retrieval result item ids contain duplicates")
        return cls(request=RetrievalRequest.load(raw.get("request")), item_ids=list(item_ids))


@dataclass
class RetrievalState:
    items: dict[str, RetrievalItem] = field(default_factory=dict)
    results: list[RetrievalResultSnapshot] = field(default_factory=list)
    current_request_id: str | None = None
    current_item_ids: list[str] = field(default_factory=list)

    def admit(self, item: RetrievalItem) -> bool:
        existing = self.items.get(item.item_id)
        if existing is not None:
            immutable_existing = existing.dump()
            immutable_candidate = item.dump()
            # Supersession is a later kernel-owned transition, so it is not
            # part of immutable identity equality for repeated admission.
            immutable_candidate["superseded_by"] = immutable_existing["superseded_by"]
            if immutable_existing != immutable_candidate:
                raise IntegrityError("retrieval item_id collision with different content or provenance")
            return False

        self.items[item.item_id] = item
        return True

    def supersede(self, old_item_id: str, new_item_id: str) -> None:
        if old_item_id == new_item_id:
            raise IntegrityError("retrieval item cannot supersede itself")
        old = self.items.get(old_item_id)
        new = self.items.get(new_item_id)
        if old is None or new is None:
            raise IntegrityError("retrieval supersession requires both admitted items")
        if old.source_id != new.source_id or old.source_locator != new.source_locator:
            raise IntegrityError("retrieval supersession requires the same source identity and locator")
        if old.superseded_by is not None and old.superseded_by != new_item_id:
            raise IntegrityError("retrieval item already has a different supersession target")
        if new.superseded_by is not None:
            raise IntegrityError("retrieval supersession target must itself be current")
        old.superseded_by = new_item_id
        # Historical request snapshots remain immutable. If the superseded item
        # was the current model-visible snapshot, clear that pointer rather than
        # mutating history. A subsequent retrieval request may expose the new
        # current item.
        if old_item_id in self.current_item_ids:
            self.current_request_id = None
            self.current_item_ids = []

    def record_result(self, request: RetrievalRequest, item_ids: list[str]) -> None:
        if len(item_ids) != len(set(item_ids)):
            raise IntegrityError("retrieval result contains duplicate item ids")
        for item_id in item_ids:
            item = self.items.get(item_id)
            if item is None:
                raise IntegrityError("retrieval result references missing admitted item")
            if item.superseded_by is not None:
                raise IntegrityError("retrieval result cannot expose a superseded item as current")

        candidate = RetrievalResultSnapshot(request=request, item_ids=list(item_ids))
        for existing in self.results:
            if existing.request.request_id == request.request_id:
                if existing.dump() != candidate.dump():
                    raise IntegrityError("retrieval request id collision with different result snapshot")
                self.current_request_id = request.request_id
                self.current_item_ids = list(item_ids)
                return

        self.results.append(candidate)
        self.current_request_id = request.request_id
        self.current_item_ids = list(item_ids)

    def dump(self) -> dict[str, Any]:
        return {
            "schema_version": "retrieval-state-v1",
            "items": {key: item.dump() for key, item in sorted(self.items.items())},
            "results": [result.dump() for result in self.results],
            "current_request_id": self.current_request_id,
            "current_item_ids": list(self.current_item_ids),
        }

    @classmethod
    def load(cls, raw: Any) -> "RetrievalState":
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise IntegrityError("retrieval state snapshot is malformed")
        if raw and raw.get("schema_version") not in (None, "retrieval-state-v1"):
            raise IntegrityError("unsupported retrieval state schema")

        items_raw = raw.get("items", {})
        if not isinstance(items_raw, dict):
            raise IntegrityError("retrieval state items are malformed")
        items: dict[str, RetrievalItem] = {}
        for key, item_raw in items_raw.items():
            item = RetrievalItem.load(item_raw)
            if str(key) != item.item_id:
                raise IntegrityError("retrieval state item map key mismatch")
            if item.item_id in items:
                raise IntegrityError("duplicate retrieval item id")
            items[item.item_id] = item

        results_raw = raw.get("results", [])
        if not isinstance(results_raw, list):
            raise IntegrityError("retrieval state results are malformed")
        results = [RetrievalResultSnapshot.load(item) for item in results_raw]
        request_ids = [item.request.request_id for item in results]
        if len(request_ids) != len(set(request_ids)):
            raise IntegrityError("duplicate retrieval request id")

        for result in results:
            for item_id in result.item_ids:
                if item_id not in items:
                    raise IntegrityError("retrieval history references missing item")

        current_request_id = raw.get("current_request_id")
        if current_request_id is not None:
            current_request_id = str(current_request_id)
            if current_request_id not in set(request_ids):
                raise IntegrityError("current retrieval request id is missing from history")

        current_item_ids = raw.get("current_item_ids", [])
        if not isinstance(current_item_ids, list) or not all(isinstance(x, str) for x in current_item_ids):
            raise IntegrityError("current retrieval item ids are malformed")
        if len(current_item_ids) != len(set(current_item_ids)):
            raise IntegrityError("current retrieval item ids contain duplicates")
        for item_id in current_item_ids:
            item = items.get(item_id)
            if item is None:
                raise IntegrityError("current retrieval references missing item")
            if item.superseded_by is not None:
                raise IntegrityError("current retrieval references superseded item")

        if current_request_id is not None:
            matching = next(item for item in results if item.request.request_id == current_request_id)
            if matching.item_ids != list(current_item_ids):
                raise IntegrityError("current retrieval ids disagree with current request snapshot")
        elif current_item_ids:
            raise IntegrityError("current retrieval ids exist without a current request")

        for item in items.values():
            if item.superseded_by is not None:
                target = items.get(item.superseded_by)
                if target is None:
                    raise IntegrityError("retrieval supersession points to missing item")
                if item.item_id == target.item_id:
                    raise IntegrityError("retrieval item cannot supersede itself")
                if (
                    item.source_id != target.source_id
                    or item.source_locator != target.source_locator
                ):
                    raise IntegrityError("retrieval supersession crosses source identity or locator")

        for start in items.values():
            seen_chain: set[str] = set()
            cursor = start
            while cursor.superseded_by is not None:
                if cursor.item_id in seen_chain:
                    raise IntegrityError("retrieval supersession graph contains a cycle")
                seen_chain.add(cursor.item_id)
                cursor = items[cursor.superseded_by]

        return cls(
            items=items,
            results=results,
            current_request_id=current_request_id,
            current_item_ids=list(current_item_ids),
        )


class RetrievalGateway(Protocol):
    def descriptor(self) -> dict[str, Any]: ...
    def search(self, request: RetrievalRequest) -> list[RetrievalCandidate]: ...


class LocalLexicalRetrievalGateway:
    provider_id = "local_lexical"
    provider_revision = "local-lexical-v1"
    ranking_policy_version = RetrievalPolicy.ranking_policy_version

    def __init__(
        self,
        items: Iterable[RetrievalSourceItem],
        *,
        index_revision: str = "index-v1",
    ):
        if not isinstance(index_revision, str) or not index_revision.strip():
            raise ValueError("index_revision must be a non-empty string")
        self.index_revision = index_revision
        checked: dict[tuple[str, str, str], RetrievalSourceItem] = {}
        for item in items:
            if not isinstance(item, RetrievalSourceItem):
                raise ValueError("local lexical index accepts RetrievalSourceItem objects only")
            identity = (item.source_id, item.source_revision, item.source_locator)
            existing = checked.get(identity)
            if existing is not None and existing.content_sha256 != item.content_sha256:
                raise ValueError("same source identity cannot contain different content")
            checked[identity] = item
        self._items = tuple(
            sorted(
                checked.values(),
                key=lambda item: (
                    item.source_id,
                    item.source_revision,
                    item.source_locator,
                    item.content_sha256,
                ),
            )
        )

    def descriptor(self) -> dict[str, Any]:
        index = [item.descriptor() for item in self._items]
        return {
            "provider_id": self.provider_id,
            "provider_revision": self.provider_revision,
            "index_revision": self.index_revision,
            "ranking_policy_version": self.ranking_policy_version,
            "index_hash": canonical_hash(index),
            "item_count": len(index),
            "deterministic_replay": True,
            "search_mutates_state": False,
        }

    def search(self, request: RetrievalRequest) -> list[RetrievalCandidate]:
        if not isinstance(request, RetrievalRequest):
            raise RetrievalContractError("gateway received invalid retrieval request type")
        terms = sorted(set(request.normalized_query.lower().split()))
        if not terms:
            return []

        candidates: list[RetrievalCandidate] = []
        for item in self._items:
            if item.scope != request.scope:
                continue
            haystack = item.content.lower()
            score = sum(1 for term in terms if term in haystack)
            if score <= 0:
                continue
            candidate_id = retrieval_item_id(
                provider_id=self.provider_id,
                provider_revision=self.provider_revision,
                source_id=item.source_id,
                source_revision=item.source_revision,
                source_locator=item.source_locator,
                content_sha256=item.content_sha256,
            )
            candidates.append(RetrievalCandidate(
                candidate_id=candidate_id,
                source_id=item.source_id,
                source_revision=item.source_revision,
                source_locator=item.source_locator,
                scope=item.scope,
                content=item.content,
                content_sha256=item.content_sha256,
                score=score,
                metadata=dict(item.metadata),
            ))

        candidates.sort(
            key=lambda item: (
                -item.score,
                item.source_id,
                item.content_sha256,
                item.candidate_id,
            )
        )
        deduplicated: list[RetrievalCandidate] = []
        seen: set[tuple[str, str]] = set()
        for candidate in candidates:
            identity = (candidate.source_id, candidate.content_sha256)
            if identity in seen:
                continue
            seen.add(identity)
            deduplicated.append(candidate)
            if len(deduplicated) >= request.top_k:
                break
        return deduplicated
