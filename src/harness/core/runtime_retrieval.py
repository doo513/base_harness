from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .retrieval import (
    RetrievalCandidate,
    RetrievalContractError,
    RetrievalItem,
    RetrievalPolicy,
    RetrievalRequest,
    RetrievalUnavailable,
    normalize_retrieval_query,
    retrieval_item_id,
)
from .security import Capability, Principal
from .storage import ArtifactStore, IntegrityError, canonical_hash


class RuntimeRetrievalMixin:
    """Kernel-owned Stage-08 retrieval admission and integrity boundary."""

    def _validated_gateway_descriptor(self, descriptor: Any | None = None) -> dict[str, Any]:
        if self.retrieval_gateway is None:
            raise RetrievalUnavailable("retrieval gateway is unavailable")
        raw = self.retrieval_gateway.descriptor() if descriptor is None else descriptor
        if not isinstance(raw, dict):
            raise RetrievalContractError("retrieval gateway descriptor must be an object")
        try:
            # Freeze the inspected provider descriptor into plain deterministic
            # JSON data. Later candidate validation/admission consumes this exact
            # snapshot rather than re-calling descriptor().
            encoded = json.dumps(
                raw,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            frozen = json.loads(encoded)
        except (TypeError, ValueError, OverflowError) as exc:
            raise RetrievalContractError(
                f"retrieval gateway descriptor is not deterministic JSON: {exc}"
            ) from exc

        for field in ("provider_id", "provider_revision", "index_revision"):
            value = frozen.get(field)
            if not isinstance(value, str) or not value.strip():
                raise RetrievalContractError(f"retrieval gateway descriptor requires non-empty {field}")
            if len(value) > self.retrieval_policy.max_provider_field_chars:
                raise RetrievalContractError(
                    f"retrieval gateway {field} exceeds max_provider_field_chars"
                )

        index_hash = frozen.get("index_hash")
        if not isinstance(index_hash, str) or re.fullmatch(r"[0-9a-f]{64}", index_hash) is None:
            raise RetrievalContractError("retrieval gateway index_hash must be lowercase sha256 hex")
        if frozen.get("ranking_policy_version") != self.retrieval_policy.ranking_policy_version:
            raise RetrievalContractError("retrieval gateway ranking policy version mismatch")
        if frozen.get("deterministic_replay") is not True:
            raise RetrievalContractError("retrieval gateway must declare deterministic_replay=true")
        if frozen.get("search_mutates_state") is not False:
            raise RetrievalContractError("retrieval gateway must declare search_mutates_state=false")
        item_count = frozen.get("item_count")
        if not isinstance(item_count, int) or isinstance(item_count, bool) or item_count < 0:
            raise RetrievalContractError("retrieval gateway item_count must be a non-negative integer")
        return frozen

    def _retrieval_config_descriptor(self) -> dict[str, Any]:
        gateway = self.retrieval_gateway
        gateway_descriptor = None
        if gateway is not None:
            gateway_descriptor = {
                "implementation": self._source_descriptor(gateway),
                "provider": self._validated_gateway_descriptor(),
            }
        return {
            "policy": self.retrieval_policy.descriptor(),
            "gateway": gateway_descriptor,
        }

    def _expected_retrieval_request_id(
        self,
        *,
        normalized_query: str,
        scope: str,
        top_k: int,
        requested_step: int,
        strategy_generation: int,
        provider: dict[str, Any],
    ) -> str:
        return canonical_hash({
            "run_id": self.run_id,
            "step": int(requested_step),
            "strategy_generation": int(strategy_generation),
            "query": normalized_query,
            "scope": scope,
            "top_k": int(top_k),
            "provider": provider,
            "policy_version": self.retrieval_policy.schema_version,
        })

    def _build_retrieval_request(
        self,
        query: str,
        *,
        provider: dict[str, Any],
    ) -> RetrievalRequest:
        if not self.retrieval_policy.enabled:
            raise RetrievalUnavailable("retrieval is disabled by policy")
        if self.retrieval_gateway is None:
            raise RetrievalUnavailable("retrieval gateway is unavailable")

        normalized = normalize_retrieval_query(query)
        if not normalized:
            raise RetrievalContractError("retrieval query is empty after normalization")
        if len(normalized) > self.retrieval_policy.max_query_chars:
            raise RetrievalContractError(
                f"retrieval query exceeds max_query_chars={self.retrieval_policy.max_query_chars}"
            )

        top_k = min(
            self.retrieval_policy.default_top_k,
            self.retrieval_policy.max_admitted_per_request,
        )
        if top_k < 1:
            raise RetrievalContractError("retrieval policy permits no admitted results")

        request_id = self._expected_retrieval_request_id(
            normalized_query=normalized,
            scope=self.retrieval_policy.default_scope,
            top_k=top_k,
            requested_step=int(self.state.step),
            strategy_generation=int(self.state.strategy_generation),
            provider=provider,
        )
        return RetrievalRequest(
            request_id=request_id,
            query=normalized,
            normalized_query=normalized,
            scope=self.retrieval_policy.default_scope,
            top_k=top_k,
            requested_step=int(self.state.step),
            strategy_generation=int(self.state.strategy_generation),
        )

    def _validate_request_snapshot(
        self,
        request: RetrievalRequest,
        *,
        provider: dict[str, Any],
    ) -> None:
        normalized = normalize_retrieval_query(request.query)
        if not normalized or normalized != request.normalized_query:
            raise IntegrityError("retrieval request query normalization mismatch")
        if len(normalized) > self.retrieval_policy.max_query_chars:
            raise IntegrityError("persisted retrieval query exceeds current policy bound")
        if request.scope != self.retrieval_policy.default_scope:
            raise IntegrityError("persisted retrieval request scope differs from kernel policy")
        expected_top_k = min(
            self.retrieval_policy.default_top_k,
            self.retrieval_policy.max_admitted_per_request,
        )
        if request.top_k != expected_top_k:
            raise IntegrityError("persisted retrieval request top_k differs from kernel policy")
        if request.requested_step < 0 or request.requested_step > int(self.state.step):
            raise IntegrityError("persisted retrieval request step is outside durable run state")
        if request.strategy_generation < 0 or request.strategy_generation > int(self.state.strategy_generation):
            raise IntegrityError("persisted retrieval strategy generation is outside durable run state")
        expected_id = self._expected_retrieval_request_id(
            normalized_query=request.normalized_query,
            scope=request.scope,
            top_k=request.top_k,
            requested_step=request.requested_step,
            strategy_generation=request.strategy_generation,
            provider=provider,
        )
        if request.request_id != expected_id:
            raise IntegrityError("persisted retrieval request id does not match kernel-derived identity")

    @staticmethod
    def _candidate_sort_key(candidate: RetrievalCandidate):
        return (
            -candidate.score,
            candidate.source_id,
            candidate.content_sha256,
            candidate.candidate_id,
        )

    def _validate_source_field(self, name: str, value: Any, max_chars: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise RetrievalContractError(f"retrieval candidate {name} must be a non-empty string")
        if len(value) > max_chars:
            raise RetrievalContractError(f"retrieval candidate {name} exceeds configured bound")
        return value

    def _normalize_gateway_candidates(
        self,
        candidates: Any,
        *,
        request: RetrievalRequest,
        provider: dict[str, Any],
    ) -> list[RetrievalCandidate]:
        if not isinstance(candidates, list):
            raise RetrievalContractError("retrieval gateway must return a list")
        checked: list[RetrievalCandidate] = []
        provider_id = provider["provider_id"]
        provider_revision = provider["provider_revision"]
        for candidate in candidates:
            if not isinstance(candidate, RetrievalCandidate):
                raise RetrievalContractError("retrieval gateway returned an invalid candidate type")
            source_id = self._validate_source_field(
                "source_id", candidate.source_id, self.retrieval_policy.max_source_id_chars
            )
            source_revision = self._validate_source_field(
                "source_revision",
                candidate.source_revision,
                self.retrieval_policy.max_source_revision_chars,
            )
            source_locator = self._validate_source_field(
                "source_locator",
                candidate.source_locator,
                self.retrieval_policy.max_source_locator_chars,
            )
            if candidate.scope != request.scope:
                raise RetrievalContractError("retrieval gateway returned a candidate outside request scope")
            if candidate.score < 0:
                raise RetrievalContractError("retrieval candidate score must be non-negative")
            content_bytes = candidate.content.encode("utf-8")
            if len(content_bytes) > self.retrieval_policy.max_content_bytes_per_item:
                raise RetrievalContractError("retrieval candidate exceeds per-item content byte bound")
            expected_digest = hashlib.sha256(content_bytes).hexdigest()
            if candidate.content_sha256 != expected_digest:
                raise RetrievalContractError("retrieval candidate content digest mismatch")
            expected_id = retrieval_item_id(
                provider_id=provider_id,
                provider_revision=provider_revision,
                source_id=source_id,
                source_revision=source_revision,
                source_locator=source_locator,
                content_sha256=candidate.content_sha256,
            )
            if candidate.candidate_id != expected_id:
                raise RetrievalContractError("retrieval candidate identity is not provider-bound")
            existing = self.state.retrieval.items.get(expected_id)
            if existing is not None and existing.superseded_by is not None:
                continue
            sanitized_metadata = self.retrieval_policy.sanitize_metadata(candidate.metadata)
            checked.append(RetrievalCandidate(
                candidate_id=candidate.candidate_id,
                source_id=source_id,
                source_revision=source_revision,
                source_locator=source_locator,
                scope=candidate.scope,
                content=candidate.content,
                content_sha256=candidate.content_sha256,
                score=candidate.score,
                metadata=sanitized_metadata,
            ))

        checked.sort(key=self._candidate_sort_key)
        deduplicated: list[RetrievalCandidate] = []
        seen: set[tuple[str, str]] = set()
        total_bytes = 0
        for candidate in checked:
            identity = (candidate.source_id, candidate.content_sha256)
            if identity in seen:
                continue
            candidate_bytes = len(candidate.content.encode("utf-8"))
            if total_bytes + candidate_bytes > self.retrieval_policy.max_total_content_bytes_per_request:
                raise RetrievalContractError("retrieval result set exceeds per-request content byte bound")
            seen.add(identity)
            deduplicated.append(candidate)
            total_bytes += candidate_bytes
            if len(deduplicated) >= min(
                request.top_k,
                self.retrieval_policy.max_admitted_per_request,
            ):
                break
        return deduplicated

    def _preflight_retrieval_capacity(
        self,
        *,
        request: RetrievalRequest,
        candidates: list[RetrievalCandidate],
    ) -> None:
        existing_request = any(
            result.request.request_id == request.request_id
            for result in self.state.retrieval.results
        )
        if not existing_request and len(self.state.retrieval.results) >= self.retrieval_policy.max_request_snapshots:
            raise RetrievalContractError(
                "retrieval request history capacity reached; fail-closed policy forbids eviction"
            )
        new_item_ids = {
            candidate.candidate_id
            for candidate in candidates
            if candidate.candidate_id not in self.state.retrieval.items
        }
        if len(self.state.retrieval.items) + len(new_item_ids) > self.retrieval_policy.max_durable_items:
            raise RetrievalContractError(
                "retrieval durable item capacity reached; fail-closed policy forbids eviction"
            )

    def _admit_retrieval_candidate(
        self,
        candidate: RetrievalCandidate,
        *,
        provider: dict[str, Any],
    ) -> RetrievalItem:
        provider_id = provider["provider_id"]
        provider_revision = provider["provider_revision"]
        item_id = retrieval_item_id(
            provider_id=provider_id,
            provider_revision=provider_revision,
            source_id=candidate.source_id,
            source_revision=candidate.source_revision,
            source_locator=candidate.source_locator,
            content_sha256=candidate.content_sha256,
        )
        if item_id != candidate.candidate_id:
            raise RetrievalContractError("candidate identity changed during admission")

        sanitized_metadata = self.retrieval_policy.sanitize_metadata(candidate.metadata)
        existing = self.state.retrieval.items.get(item_id)
        if existing is not None:
            if existing.superseded_by is not None:
                raise RetrievalContractError("superseded retrieval item cannot be re-admitted as current")
            if (
                existing.source_id != candidate.source_id
                or existing.source_revision != candidate.source_revision
                or existing.source_locator != candidate.source_locator
                or existing.provider_id != provider_id
                or existing.provider_revision != provider_revision
                or existing.content_sha256 != candidate.content_sha256
                or existing.metadata != sanitized_metadata
            ):
                raise IntegrityError("existing retrieval item disagrees with repeated candidate")
            raw = self.artifacts.verified_read_bytes(existing.content_ref)
            if hashlib.sha256(raw).hexdigest() != candidate.content_sha256:
                raise IntegrityError("existing retrieval artifact failed repeated admission integrity")
            if len(raw) > self.retrieval_policy.max_content_bytes_per_item:
                raise IntegrityError("existing retrieval artifact exceeds current content byte bound")
            try:
                if raw.decode("utf-8") != candidate.content:
                    raise IntegrityError("existing retrieval artifact content differs from repeated candidate")
            except UnicodeDecodeError as exc:
                raise IntegrityError(f"existing retrieval content is not valid UTF-8: {exc}") from exc
            return existing

        artifact_ref = self.artifacts.put_text(
            f"retrieval_{item_id[:24]}.txt",
            candidate.content,
        )
        raw = self.artifacts.verified_read_bytes(artifact_ref)
        actual_digest = hashlib.sha256(raw).hexdigest()
        if len(raw) > self.retrieval_policy.max_content_bytes_per_item:
            raise IntegrityError("retrieval artifact exceeds content byte bound after storage")
        if actual_digest != candidate.content_sha256:
            raise IntegrityError("retrieval artifact digest differs from admitted candidate")
        if ArtifactStore.digest_from_ref(artifact_ref) != actual_digest:
            raise IntegrityError("retrieval artifact reference digest mismatch")

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IntegrityError(f"retrieval artifact is not valid UTF-8: {exc}") from exc
        preview_limit = self.retrieval_policy.max_preview_chars_per_item
        preview = text[:preview_limit]
        preview_truncated = len(text) > len(preview)
        item = RetrievalItem(
            item_id=item_id,
            content_ref=artifact_ref,
            content_sha256=actual_digest,
            source_id=candidate.source_id,
            source_revision=candidate.source_revision,
            source_locator=candidate.source_locator,
            admitted_step=int(self.state.step),
            provider_id=provider_id,
            provider_revision=provider_revision,
            preview=preview,
            preview_truncated=preview_truncated,
            content_chars=len(text),
            metadata=sanitized_metadata,
        )
        self.capability_policy.require(Principal.KERNEL, Capability.STATE_COMMIT)
        inserted = self.state.retrieval.admit(item)
        if inserted:
            self.state.artifacts.append(artifact_ref)
            if artifact_ref not in self.state.evidence_refs:
                self.state.evidence_refs.append(artifact_ref)
            self.metrics["retrieval_items_admitted"] = int(
                self.metrics.get("retrieval_items_admitted", 0)
            ) + 1
        return item

    def _handle_retrieval_request(self, query: str) -> list[str]:
        provider_before = self._validated_gateway_descriptor()
        request = self._build_retrieval_request(query, provider=provider_before)
        candidates = self.retrieval_gateway.search(request)
        provider_after = self._validated_gateway_descriptor()
        if provider_before != provider_after:
            raise RetrievalContractError(
                "retrieval gateway mutated its declared index/provider state during search"
            )

        normalized = self._normalize_gateway_candidates(
            candidates,
            request=request,
            provider=provider_before,
        )
        self._preflight_retrieval_capacity(request=request, candidates=normalized)
        item_ids: list[str] = []
        for candidate in normalized:
            item = self._admit_retrieval_candidate(candidate, provider=provider_before)
            item_ids.append(item.item_id)

        self.capability_policy.require(Principal.KERNEL, Capability.STATE_COMMIT)
        self.state.retrieval.record_result(request, item_ids)
        self.metrics["retrieval_requests"] = int(self.metrics.get("retrieval_requests", 0)) + 1
        self.metrics["retrieval_results"] = int(self.metrics.get("retrieval_results", 0)) + len(item_ids)
        self.log("retrieval.admitted", {
            "request": request.dump(),
            "item_ids": list(item_ids),
            "provider": provider_before,
            "trust": "untrusted_retrieval",
            "instruction_authority": "none",
            "direct_fact_mutations": 0,
            "direct_completion_mutations": 0,
            "progress_credit": 0,
        })
        return item_ids

    def _supersede_retrieval_item(self, old_item_id: str, new_item_id: str) -> None:
        """Apply an explicit kernel-owned supersession transition."""
        self.capability_policy.require(Principal.KERNEL, Capability.STATE_COMMIT)
        before_facts = canonical_hash({
            key: claim.dump() for key, claim in sorted(self.state.facts.items())
        })
        before_completed = bool(self.state.completed)
        self.state.retrieval.supersede(old_item_id, new_item_id)
        if before_facts != canonical_hash({
            key: claim.dump() for key, claim in sorted(self.state.facts.items())
        }):
            raise IntegrityError("retrieval supersession unexpectedly mutated verified facts")
        if before_completed != bool(self.state.completed):
            raise IntegrityError("retrieval supersession unexpectedly mutated completion state")
        self.log("retrieval.superseded", {
            "old_item_id": old_item_id,
            "new_item_id": new_item_id,
            "kernel_owned": True,
            "direct_fact_mutations": 0,
            "direct_completion_mutations": 0,
            "progress_credit": 0,
        })

    def _validate_retrieval_state_integrity(self, *, current_only: bool = False) -> None:
        retrieval = self.state.retrieval
        if not self.retrieval_policy.enabled:
            if retrieval.items or retrieval.results or retrieval.current_item_ids:
                raise IntegrityError("durable retrieval state exists while retrieval policy is disabled")
            return
        if self.retrieval_gateway is None:
            raise IntegrityError("retrieval policy enabled but gateway is unavailable")

        try:
            provider = self._validated_gateway_descriptor()
        except (RetrievalContractError, RetrievalUnavailable) as exc:
            raise IntegrityError(f"retrieval gateway contract invalid during integrity check: {exc}") from exc
        provider_id = provider["provider_id"]
        provider_revision = provider["provider_revision"]

        if len(retrieval.items) > self.retrieval_policy.max_durable_items:
            raise IntegrityError("durable retrieval item count exceeds current policy")
        if len(retrieval.results) > self.retrieval_policy.max_request_snapshots:
            raise IntegrityError("durable retrieval request history exceeds current policy")

        results_to_check = retrieval.results
        if current_only:
            results_to_check = []
            if retrieval.current_request_id is not None:
                results_to_check = [
                    result for result in retrieval.results
                    if result.request.request_id == retrieval.current_request_id
                ]
                if len(results_to_check) != 1:
                    raise IntegrityError("current retrieval request does not resolve uniquely")
        for result in results_to_check:
            self._validate_request_snapshot(result.request, provider=provider)
            if len(result.item_ids) > self.retrieval_policy.max_admitted_per_request:
                raise IntegrityError("persisted retrieval result exceeds item-count admission bound")

        if current_only:
            selected_ids = list(retrieval.current_item_ids)
        else:
            selected_ids = sorted(retrieval.items)

        item_bytes: dict[str, int] = {}
        for item_id in selected_ids:
            item = retrieval.items.get(item_id)
            if item is None:
                raise IntegrityError("retrieval state references missing item")
            if item.trust != "untrusted_retrieval" or item.instruction_authority != "none":
                raise IntegrityError("retrieval item authority fields were corrupted")
            if item.provider_id != provider_id or item.provider_revision != provider_revision:
                raise IntegrityError("retrieval item provider identity differs from configured gateway")
            if len(item.provider_id) > self.retrieval_policy.max_provider_field_chars or len(item.provider_revision) > self.retrieval_policy.max_provider_field_chars:
                raise IntegrityError("persisted retrieval provider identity exceeds policy bounds")
            if not item.source_id or len(item.source_id) > self.retrieval_policy.max_source_id_chars:
                raise IntegrityError("persisted retrieval source_id violates policy bounds")
            if not item.source_revision or len(item.source_revision) > self.retrieval_policy.max_source_revision_chars:
                raise IntegrityError("persisted retrieval source_revision violates policy bounds")
            if not item.source_locator or len(item.source_locator) > self.retrieval_policy.max_source_locator_chars:
                raise IntegrityError("persisted retrieval source_locator violates policy bounds")
            if item.admitted_step < 0 or item.admitted_step > int(self.state.step):
                raise IntegrityError("persisted retrieval admitted_step is outside durable run state")
            if self.retrieval_policy.sanitize_metadata(item.metadata) != item.metadata:
                raise IntegrityError("persisted retrieval metadata exceeds or disagrees with policy bounds")
            expected_id = retrieval_item_id(
                provider_id=item.provider_id,
                provider_revision=item.provider_revision,
                source_id=item.source_id,
                source_revision=item.source_revision,
                source_locator=item.source_locator,
                content_sha256=item.content_sha256,
            )
            if item.item_id != expected_id:
                raise IntegrityError("retrieval item identity mismatch")

            raw = self.artifacts.verified_read_bytes(item.content_ref)
            item_bytes[item_id] = len(raw)
            if len(raw) > self.retrieval_policy.max_content_bytes_per_item:
                raise IntegrityError("persisted retrieval artifact exceeds per-item content byte bound")
            actual_digest = hashlib.sha256(raw).hexdigest()
            if actual_digest != item.content_sha256:
                raise IntegrityError("retrieval content digest mismatch")
            if ArtifactStore.digest_from_ref(item.content_ref) != item.content_sha256:
                raise IntegrityError("retrieval content ref digest mismatch")

            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise IntegrityError(f"retrieval content is not valid UTF-8: {exc}") from exc
            expected_preview = text[: self.retrieval_policy.max_preview_chars_per_item]
            if item.preview != expected_preview:
                raise IntegrityError("retrieval item preview disagrees with verified content")
            if item.preview_truncated != (len(text) > len(expected_preview)):
                raise IntegrityError("retrieval item preview truncation flag mismatch")
            if item.content_chars != len(text):
                raise IntegrityError("retrieval item content length mismatch")

        if not current_only:
            for result in retrieval.results:
                total = 0
                for item_id in result.item_ids:
                    if item_id not in item_bytes:
                        raise IntegrityError("retrieval history references unverified item")
                    total += item_bytes[item_id]
                if total > self.retrieval_policy.max_total_content_bytes_per_request:
                    raise IntegrityError("persisted retrieval result exceeds per-request content byte bound")

        if retrieval.current_request_id is not None:
            matching = [
                result for result in retrieval.results
                if result.request.request_id == retrieval.current_request_id
            ]
            if len(matching) != 1:
                raise IntegrityError("current retrieval request does not resolve uniquely")
            if matching[0].item_ids != retrieval.current_item_ids:
                raise IntegrityError("current retrieval request snapshot differs from current item ids")

        for item in retrieval.items.values():
            if item.superseded_by is not None and item.superseded_by not in retrieval.items:
                raise IntegrityError("retrieval supersession target is missing")

    def _project_retrieval_context(self, projected):
        """Compose bounded Stage-08 data into the Stage-07 governed projection."""
        if not self.retrieval_policy.enabled:
            return projected

        self._validate_retrieval_state_integrity(current_only=True)
        retrieval = self.state.retrieval
        raw_ids = list(retrieval.current_item_ids)
        selected_ids = raw_ids[: self.retrieval_policy.max_context_items]
        remaining_preview = self.retrieval_policy.max_total_context_preview_chars
        remaining_metadata = self.retrieval_policy.max_total_context_metadata_chars
        visible: list[dict[str, Any]] = []
        visible_chars = 0
        visible_metadata_chars = 0

        for item_id in selected_ids:
            item = retrieval.items[item_id]
            per_item = min(
                self.retrieval_policy.max_preview_chars_per_item,
                remaining_preview,
            )
            text = item.preview[:per_item]
            truncated = item.preview_truncated or len(item.preview) > len(text)
            remaining_preview = max(0, remaining_preview - len(text))
            visible_chars += len(text)
            metadata, metadata_chars = self.retrieval_policy.project_metadata(
                item.metadata,
                remaining_total=remaining_metadata,
            )
            remaining_metadata = max(0, remaining_metadata - metadata_chars)
            visible_metadata_chars += metadata_chars
            visible.append({
                "item_id": item.item_id,
                "content_ref": item.content_ref,
                "content_sha256": item.content_sha256,
                "source_id": item.source_id,
                "source_revision": item.source_revision,
                "source_locator": item.source_locator,
                "provider_id": item.provider_id,
                "provider_revision": item.provider_revision,
                "trust": "untrusted_retrieval",
                "instruction_authority": "none",
                "preview": {
                    "format": "text",
                    "text": text,
                    "truncated": truncated,
                    "original_chars": item.content_chars,
                    "visible_chars": len(text),
                },
                "metadata": metadata,
            })

        projected["untrusted"]["retrieval"] = visible
        projected["projection"]["retrieval_policy"] = self.retrieval_policy.descriptor()
        projected["projection"]["retrieval_stats"] = {
            "raw_current_item_count": len(raw_ids),
            "selected_current_item_count": len(selected_ids),
            "omitted_current_item_count": max(0, len(raw_ids) - len(selected_ids)),
            "visible_preview_chars": visible_chars,
            "visible_metadata_chars": visible_metadata_chars,
            "durable_item_count": len(retrieval.items),
            "request_snapshot_count": len(retrieval.results),
            "model_visible_trust": "untrusted_retrieval",
            "instruction_authority": "none",
            "retrieval_counts_as_progress": False,
        }
        projected["projection"]["omissions"]["retrieval_items"] = max(
            0, len(raw_ids) - len(selected_ids)
        )
        return projected
