from __future__ import annotations

from dataclasses import replace
import json
import tempfile
from pathlib import Path

from harness.core.retrieval import (
    LocalLexicalRetrievalGateway,
    RetrievalContractError,
    RetrievalPolicy,
    RetrievalResultSnapshot,
)
from harness.core.storage import IntegrityError

from stage8_probe_support import gateway, runtime, source


class MutatingGateway(LocalLexicalRetrievalGateway):
    def __init__(self, items):
        super().__init__(items)
        self.counter = 0

    def descriptor(self):
        descriptor = super().descriptor()
        descriptor["counter"] = self.counter
        return descriptor

    def search(self, request):
        result = super().search(request)
        self.counter += 1
        return result


def main() -> int:
    outcomes = {}
    with tempfile.TemporaryDirectory(prefix="vsh-stage8-adv-") as tmp:
        root = Path(tmp)

        mutating = runtime(
            root,
            "mutating",
            retrieval_gateway=MutatingGateway([source("a", "needle")]),
        )
        blocked = False
        try:
            mutating._handle_retrieval_request("needle")
        except RetrievalContractError:
            blocked = True
        outcomes["provider_mutation_blocked"] = {
            "passed": blocked and not mutating.state.retrieval.items,
            "admitted_items": len(mutating.state.retrieval.items),
        }

        bound_policy = RetrievalPolicy(
            enabled=True,
            default_top_k=1,
            max_admitted_per_request=1,
            max_content_bytes_per_item=8,
            max_total_content_bytes_per_request=8,
        )
        oversized = runtime(
            root,
            "oversized",
            retrieval_gateway=gateway([source("a", "needle-too-large")]),
            retrieval_policy=bound_policy,
        )
        blocked = False
        try:
            oversized._handle_retrieval_request("needle")
        except RetrievalContractError:
            blocked = True
        outcomes["oversized_content_atomic_block"] = {
            "passed": blocked
            and not oversized.state.retrieval.items
            and not oversized.state.artifacts
            and not oversized.state.evidence_refs,
            "admitted_items": len(oversized.state.retrieval.items),
            "artifact_refs": len(oversized.state.artifacts),
        }

        supersede = runtime(
            root,
            "supersede",
            retrieval_gateway=gateway([
                source("doc", "needle old", revision="r1", locator="same"),
                source("doc", "needle new", revision="r2", locator="same"),
            ]),
        )
        ids = supersede._handle_retrieval_request("needle")
        by_revision = {
            supersede.state.retrieval.items[item_id].source_revision: item_id
            for item_id in ids
        }
        old_id, new_id = by_revision["r1"], by_revision["r2"]
        no_implicit = (
            supersede.state.retrieval.items[old_id].superseded_by is None
            and supersede.state.retrieval.items[new_id].superseded_by is None
        )
        supersede._supersede_retrieval_item(old_id, new_id)
        supersede.state.step += 1
        current = supersede._handle_retrieval_request("needle")
        outcomes["explicit_supersession_only"] = {
            "passed": no_implicit
            and supersede.state.retrieval.items[old_id].superseded_by == new_id
            and old_id not in current
            and new_id in current,
            "old_reentered_current": old_id in current,
        }

        request_id_rt = runtime(
            root,
            "request-id",
            retrieval_gateway=gateway([source("a", "needle")]),
        )
        request_id_rt._handle_retrieval_request("needle")
        original = request_id_rt.state.retrieval.results[0]
        request_id_rt.state.retrieval.results[0] = RetrievalResultSnapshot(
            request=replace(original.request, request_id="0" * 64),
            item_ids=list(original.item_ids),
        )
        blocked = False
        try:
            request_id_rt._validate_retrieval_state_integrity()
        except IntegrityError:
            blocked = True
        outcomes["forged_request_identity_blocked"] = {
            "passed": blocked,
        }

        history_policy = RetrievalPolicy(
            enabled=True,
            default_top_k=1,
            max_admitted_per_request=1,
            max_durable_items=1,
            max_request_snapshots=2,
        )
        history = runtime(
            root,
            "history",
            retrieval_gateway=gateway([
                source("a", "one needle"),
                source("b", "two needle"),
            ]),
            retrieval_policy=history_policy,
        )
        history._handle_retrieval_request("one")
        before_ids = set(history.state.retrieval.items)
        blocked = False
        try:
            history._handle_retrieval_request("two")
        except RetrievalContractError:
            blocked = True
        outcomes["history_capacity_fail_closed"] = {
            "passed": blocked and set(history.state.retrieval.items) == before_ids,
            "durable_items": len(history.state.retrieval.items),
        }

    summary = {
        "all_passed": all(item["passed"] for item in outcomes.values()),
        "scenario_count": len(outcomes),
        "partial_admission_failures": 0 if outcomes["oversized_content_atomic_block"]["passed"] else 1,
        "implicit_supersessions": 0 if outcomes["explicit_supersession_only"]["passed"] else 1,
    }
    print(json.dumps({
        "stage": "08",
        "probe": "retrieval-adversarial-rc1",
        "outcomes": outcomes,
        "summary": summary,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
