from __future__ import annotations

import hashlib

from .retrieval import (
    RetrievalCandidate,
    RetrievalContractError,
    RetrievalItem,
    RetrievalRequest,
    RetrievalState,
    normalize_retrieval_query,
    retrieval_item_id,
)
from .runtime_retrieval import RuntimeRetrievalMixin as _BaseRuntimeRetrievalMixin
from .security import Capability, Principal
from .storage import ArtifactStore, IntegrityError


class RuntimeRetrievalMixin(_BaseRuntimeRetrievalMixin):
    """Stage-08 kernel boundary with deterministic request framing and atomic state admission.

    Provider artifact writes may leave unreferenced content-addressed files if a
    later preparation step fails, but HarnessState, retrieval history, artifact
    references, evidence references, and metrics are committed only after the
    complete batch has been prepared and verified.
    """

    @staticmethod
    def _kernel_query_terms(actor_request: str) -> str:
        """Normalize the explicit Actor retrieval request deterministically.

        Stage 08 keeps the Actor-controlled field explicit and inspectable while
        Kernel-owned scope/top-k/provider/ranking/admission form the durable
        request descriptor. More semantic query planning is intentionally left
        for a later stage rather than silently changing persisted query meaning.
        """
        return normalize_retrieval_query(actor_request)

    def _build_retrieval_request(
        self,
        query: str,
        *,
        provider: dict,
    ) -> RetrievalRequest:
        if not self.retrieval_policy.enabled:
            from .retrieval import RetrievalUnavailable

            raise RetrievalUnavailable("retrieval is disabled by policy")
        if self.retrieval_gateway is None:
            from .retrieval import RetrievalUnavailable

            raise RetrievalUnavailable("retrieval gateway is unavailable")

        actor_request = normalize_retrieval_query(query)
        if not actor_request:
            raise RetrievalContractError("retrieval query is empty after normalization")
        if len(actor_request) > self.retrieval_policy.max_query_chars:
            raise RetrievalContractError(
                f"retrieval query exceeds max_query_chars={self.retrieval_policy.max_query_chars}"
            )
        kernel_query = self._kernel_query_terms(actor_request)
        if not kernel_query:
            raise RetrievalContractError("kernel-derived retrieval query is empty")

        top_k = min(
            self.retrieval_policy.default_top_k,
            self.retrieval_policy.max_admitted_per_request,
        )
        if top_k < 1:
            raise RetrievalContractError("retrieval policy permits no admitted results")

        request_id = self._expected_retrieval_request_id(
            normalized_query=kernel_query,
            scope=self.retrieval_policy.default_scope,
            top_k=top_k,
            requested_step=int(self.state.step),
            strategy_generation=int(self.state.strategy_generation),
            provider=provider,
        )
        return RetrievalRequest(
            request_id=request_id,
            query=actor_request,
            normalized_query=kernel_query,
            scope=self.retrieval_policy.default_scope,
            top_k=top_k,
            requested_step=int(self.state.step),
            strategy_generation=int(self.state.strategy_generation),
        )

    def _validate_request_snapshot(
        self,
        request: RetrievalRequest,
        *,
        provider: dict,
    ) -> None:
        actor_request = normalize_retrieval_query(request.query)
        if not actor_request:
            raise IntegrityError("retrieval request actor text is empty")
        if len(actor_request) > self.retrieval_policy.max_query_chars:
            raise IntegrityError("persisted retrieval query exceeds current policy bound")
        if self._kernel_query_terms(actor_request) != request.normalized_query:
            raise IntegrityError("persisted retrieval query differs from kernel-derived query")
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

    def _prepare_retrieval_candidate(
        self,
        candidate: RetrievalCandidate,
        *,
        provider: dict,
    ) -> tuple[RetrievalItem, bool, str | None]:
        """Verify/store one candidate without mutating HarnessState."""
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
            raise RetrievalContractError("candidate identity changed during admission preparation")

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
            if len(raw) > self.retrieval_policy.max_content_bytes_per_item:
                raise IntegrityError("existing retrieval artifact exceeds current content byte bound")
            if hashlib.sha256(raw).hexdigest() != candidate.content_sha256:
                raise IntegrityError("existing retrieval artifact failed repeated admission integrity")
            try:
                if raw.decode("utf-8") != candidate.content:
                    raise IntegrityError("existing retrieval artifact content differs from repeated candidate")
            except UnicodeDecodeError as exc:
                raise IntegrityError(f"existing retrieval content is not valid UTF-8: {exc}") from exc
            return existing, False, None

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

        preview = text[: self.retrieval_policy.max_preview_chars_per_item]
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
            preview_truncated=len(text) > len(preview),
            content_chars=len(text),
            metadata=sanitized_metadata,
        )
        return item, True, artifact_ref

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

        prepared: list[tuple[RetrievalItem, bool, str | None]] = []
        for candidate in normalized:
            prepared.append(
                self._prepare_retrieval_candidate(candidate, provider=provider_before)
            )

        # Build the complete next state off to the side. Any preparation or
        # state-validation failure leaves the live HarnessState untouched.
        next_retrieval = RetrievalState.load(self.state.retrieval.dump())
        next_artifacts = list(self.state.artifacts)
        next_evidence_refs = list(self.state.evidence_refs)
        item_ids: list[str] = []
        new_count = 0
        for item, is_new, artifact_ref in prepared:
            inserted = next_retrieval.admit(item)
            if inserted != is_new:
                raise IntegrityError("retrieval preparation/commit new-item classification diverged")
            item_ids.append(item.item_id)
            if inserted:
                new_count += 1
                assert artifact_ref is not None
                if artifact_ref not in next_artifacts:
                    next_artifacts.append(artifact_ref)
                if artifact_ref not in next_evidence_refs:
                    next_evidence_refs.append(artifact_ref)

        next_retrieval.record_result(request, item_ids)
        self.capability_policy.require(Principal.KERNEL, Capability.STATE_COMMIT)

        # These assignments are the state-side commit point. Content-addressed
        # files created during preparation are not authoritative until referenced
        # by this committed snapshot.
        self.state.retrieval = next_retrieval
        self.state.artifacts = next_artifacts
        self.state.evidence_refs = next_evidence_refs
        self.metrics["retrieval_items_admitted"] = int(
            self.metrics.get("retrieval_items_admitted", 0)
        ) + new_count
        self.metrics["retrieval_requests"] = int(self.metrics.get("retrieval_requests", 0)) + 1
        self.metrics["retrieval_results"] = int(self.metrics.get("retrieval_results", 0)) + len(item_ids)
        self.log("retrieval.admitted", {
            "request": request.dump(),
            "item_ids": list(item_ids),
            "provider": provider_before,
            "query_ownership": {
                "actor_field": "query",
                "kernel_owned_fields": ["scope", "top_k", "provider", "ranking", "admission"],
                "kernel_transform": "whitespace-normalize-v1",
            },
            "transaction": {
                "prepared_items": len(prepared),
                "new_items": new_count,
                "state_commit": "single_batch",
                "orphan_artifacts_non_authoritative": True,
            },
            "trust": "untrusted_retrieval",
            "instruction_authority": "none",
            "direct_fact_mutations": 0,
            "direct_completion_mutations": 0,
            "progress_credit": 0,
        })
        return item_ids
