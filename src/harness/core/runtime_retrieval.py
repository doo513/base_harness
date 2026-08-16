from __future__ import annotations

import hashlib
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

    def _retrieval_config_descriptor(self) -> dict[str, Any]:
        gateway = self.retrieval_gateway
        gateway_descriptor = None
        if gateway is not None:
            gateway_descriptor = {
                "implementation": self._source_descriptor(gateway),
                "provider": gateway.descriptor(),
            }
        return {
            "policy": self.retrieval_policy.descriptor(),
            "gateway": gateway_descriptor,
        }

    def _build_retrieval_request(self, query: str) -> RetrievalRequest:
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

        provider = self.retrieval_gateway.descriptor()
        request_body = {
            "run_id": self.run_id,
            "step": int(self.state.step),
            "strategy_generation": int(self.state.strategy_generation),
            "query": normalized,
            "scope": self.retrieval_policy.default_scope,
            "top_k": top_k,
            "provider": provider,
            "policy_version": self.retrieval_policy.schema_version,
        }
        request_id = canonical_hash(request_body)
        return RetrievalRequest(
            request_id=request_id,
            query=normalized,
            normalized_query=normalized,
            scope=self.retrieval_policy.default_scope,
            top_k=top_k,
            requested_step=int(self.state.step),
            strategy_generation=int(self.state.strategy_generation),
        )

    @staticmethod
    def _candidate_sort_key(candidate: RetrievalCandidate):
        return (
            -candidate.score,
            candidate.source_id,
            candidate.content_sha256,
            candidate.candidate_id,
        )

    def _normalize_gateway_candidates(
        self,
        candidates: Any,
        *,
        request: RetrievalRequest,
    ) -> list[RetrievalCandidate]:
        if not isinstance(candidates, list):
            raise RetrievalContractError("retrieval gateway must return a list")
        checked: list[RetrievalCandidate] = []
        for candidate in candidates:
            if not isinstance(candidate, RetrievalCandidate):
                raise RetrievalContractError("retrieval gateway returned an invalid candidate type")
            if candidate.scope != request.scope:
                raise RetrievalContractError("retrieval gateway returned a candidate outside request scope")
            if candidate.score < 0:
                raise RetrievalContractError("retrieval candidate score must be non-negative")
            expected_digest = hashlib.sha256(candidate.content.encode("utf-8")).hexdigest()
            if candidate.content_sha256 != expected_digest:
                raise RetrievalContractError("retrieval candidate content digest mismatch")
            gateway_provider = self.retrieval_gateway.descriptor()
            expected_id = retrieval_item_id(
                provider_id=str(gateway_provider.get("provider_id", "")),
                provider_revision=str(gateway_provider.get("provider_revision", "")),
                source_id=candidate.source_id,
                source_revision=candidate.source_revision,
                source_locator=candidate.source_locator,
                content_sha256=candidate.content_sha256,
            )
            if candidate.candidate_id != expected_id:
                raise RetrievalContractError("retrieval candidate identity is not provider-bound")
            existing = self.state.retrieval.items.get(expected_id)
            if existing is not None and existing.superseded_by is not None:
                # Historical revisions cannot silently re-enter the current
                # model-visible result set after a kernel supersession.
                continue
            checked.append(candidate)

        checked.sort(key=self._candidate_sort_key)
        deduplicated: list[RetrievalCandidate] = []
        seen: set[tuple[str, str]] = set()
        for candidate in checked:
            identity = (candidate.source_id, candidate.content_sha256)
            if identity in seen:
                continue
            seen.add(identity)
            deduplicated.append(candidate)
            if len(deduplicated) >= min(
                request.top_k,
                self.retrieval_policy.max_admitted_per_request,
            ):
                break
        return deduplicated

    def _admit_retrieval_candidate(self, candidate: RetrievalCandidate) -> RetrievalItem:
        provider = self.retrieval_gateway.descriptor()
        provider_id = str(provider.get("provider_id", ""))
        provider_revision = str(provider.get("provider_revision", ""))
        if not provider_id or not provider_revision:
            raise RetrievalContractError("retrieval provider descriptor lacks stable identity")

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
                or existing.metadata != self.retrieval_policy.sanitize_metadata(candidate.metadata)
            ):
                raise IntegrityError("existing retrieval item disagrees with repeated candidate")
            raw = self.artifacts.verified_read_bytes(existing.content_ref)
            if hashlib.sha256(raw).hexdigest() != candidate.content_sha256:
                raise IntegrityError("existing retrieval artifact failed repeated admission integrity")
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
        if actual_digest != candidate.content_sha256:
            raise IntegrityError("retrieval artifact digest differs from admitted candidate")
        if ArtifactStore.digest_from_ref(artifact_ref) != actual_digest:
            raise IntegrityError("retrieval artifact reference digest mismatch")

        text = raw.decode("utf-8")
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
            metadata=self.retrieval_policy.sanitize_metadata(candidate.metadata),
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
        request = self._build_retrieval_request(query)
        descriptor_before = self.retrieval_gateway.descriptor()
        candidates = self.retrieval_gateway.search(request)
        descriptor_after = self.retrieval_gateway.descriptor()
        if descriptor_before != descriptor_after:
            raise RetrievalContractError("retrieval gateway mutated its declared index/provider state during search")

        normalized = self._normalize_gateway_candidates(candidates, request=request)
        item_ids: list[str] = []
        for candidate in normalized:
            item = self._admit_retrieval_candidate(candidate)
            item_ids.append(item.item_id)

        self.capability_policy.require(Principal.KERNEL, Capability.STATE_COMMIT)
        self.state.retrieval.record_result(request, item_ids)
        self.metrics["retrieval_requests"] = int(self.metrics.get("retrieval_requests", 0)) + 1
        self.metrics["retrieval_results"] = int(self.metrics.get("retrieval_results", 0)) + len(item_ids)
        self.log("retrieval.admitted", {
            "request": request.dump(),
            "item_ids": list(item_ids),
            "provider": descriptor_after,
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

        provider = self.retrieval_gateway.descriptor()
        provider_id = str(provider.get("provider_id", ""))
        provider_revision = str(provider.get("provider_revision", ""))
        if not provider_id or not provider_revision:
            raise IntegrityError("retrieval gateway descriptor lacks stable provider identity")

        if current_only:
            selected_ids = list(retrieval.current_item_ids)
        else:
            selected_ids = sorted(retrieval.items)

        for item_id in selected_ids:
            item = retrieval.items.get(item_id)
            if item is None:
                raise IntegrityError("retrieval state references missing item")
            if item.trust != "untrusted_retrieval" or item.instruction_authority != "none":
                raise IntegrityError("retrieval item authority fields were corrupted")
            if item.provider_id != provider_id or item.provider_revision != provider_revision:
                raise IntegrityError("retrieval item provider identity differs from configured gateway")
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
        remaining = self.retrieval_policy.max_total_context_preview_chars
        visible: list[dict[str, Any]] = []
        visible_chars = 0

        for item_id in selected_ids:
            item = retrieval.items[item_id]
            per_item = min(
                self.retrieval_policy.max_preview_chars_per_item,
                remaining,
            )
            text = item.preview[:per_item]
            truncated = item.preview_truncated or len(item.preview) > len(text)
            remaining = max(0, remaining - len(text))
            visible_chars += len(text)
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
                "metadata": dict(item.metadata),
            })

        projected["untrusted"]["retrieval"] = visible
        projected["projection"]["retrieval_policy"] = self.retrieval_policy.descriptor()
        projected["projection"]["retrieval_stats"] = {
            "raw_current_item_count": len(raw_ids),
            "selected_current_item_count": len(selected_ids),
            "omitted_current_item_count": max(0, len(raw_ids) - len(selected_ids)),
            "visible_preview_chars": visible_chars,
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
