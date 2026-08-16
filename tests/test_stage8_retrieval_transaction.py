from __future__ import annotations

from pathlib import Path

import pytest

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision, ScriptedController
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.retrieval import LocalLexicalRetrievalGateway, RetrievalPolicy, RetrievalSourceItem
from harness.core.runtime import HarnessRuntime
from harness.core.storage import IntegrityError, PersistenceError, canonical_hash
from harness.profiles.base import DomainProfile


class Profile(DomainProfile):
    name = "stage8-transaction-test"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def default_goal(self):
        return GoalContract(
            goal="prove atomic retrieval admission",
            acceptance=["oracle only"],
            constraints=["retrieval remains untrusted"],
            pinned_constraints=["partial batches cannot become authoritative state"],
            task_id="stage8-transaction-test",
        )

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(True, "done"),
            name="stage8-transaction-oracle",
        )


def source(source_id: str, text: str):
    return RetrievalSourceItem(
        source_id=source_id,
        source_revision="r1",
        source_locator=source_id,
        content=text,
    )


def runtime(tmp_path, name, *, items, controller=None, resume=False):
    workspace = tmp_path / f"{name}-workspace"
    workspace.mkdir(exist_ok=True)
    profile = Profile(workspace)
    kwargs = dict(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller or ScriptedController([Decision("complete", {"reason": "done"})]),
        run_dir=tmp_path / name,
        workspace=workspace,
        retrieval_gateway=LocalLexicalRetrievalGateway(items),
        retrieval_policy=RetrievalPolicy(
            enabled=True,
            default_top_k=2,
            max_admitted_per_request=2,
            max_context_items=2,
        ),
        budget=Budget(hard_max_steps=20),
        task_revision=f"{name}-v1",
    )
    return HarnessRuntime.resume(**kwargs) if resume else HarnessRuntime(**kwargs)


def test_mid_batch_integrity_failure_leaves_live_state_unmodified(tmp_path, monkeypatch):
    rt = runtime(
        tmp_path,
        "atomic-failure",
        items=[source("a", "needle one"), source("b", "needle two")],
    )
    before_state = canonical_hash(rt.state.snapshot())
    before_metrics = dict(rt.metrics)
    before_artifacts = list(rt.state.artifacts)
    before_evidence = list(rt.state.evidence_refs)

    original = rt.artifacts.verified_read_bytes
    calls = {"count": 0}

    def fail_second(ref):
        calls["count"] += 1
        if calls["count"] == 2:
            raise IntegrityError("injected second-candidate integrity failure")
        return original(ref)

    monkeypatch.setattr(rt.artifacts, "verified_read_bytes", fail_second)
    with pytest.raises(IntegrityError, match="injected second-candidate"):
        rt._handle_retrieval_request("needle")

    assert canonical_hash(rt.state.snapshot()) == before_state
    assert rt.state.retrieval.items == {}
    assert rt.state.retrieval.results == []
    assert rt.state.artifacts == before_artifacts
    assert rt.state.evidence_refs == before_evidence
    assert rt.metrics == before_metrics


def test_storage_write_oserror_becomes_persistence_failure_and_leaves_state_clean(tmp_path, monkeypatch):
    rt = runtime(
        tmp_path,
        "write-failure",
        items=[source("a", "needle one")],
        controller=ScriptedController([Decision("retrieve", {"query": "needle"})]),
    )
    before_retrieval = canonical_hash(rt.state.retrieval.dump())

    def fail_write(*args, **kwargs):
        raise OSError("injected read-only filesystem")

    monkeypatch.setattr(rt.artifacts, "put_text", fail_write)
    with pytest.raises(PersistenceError, match="retrieval artifact write failed"):
        rt._handle_retrieval_request("needle")
    assert canonical_hash(rt.state.retrieval.dump()) == before_retrieval
    assert rt.state.artifacts == []
    assert rt.state.evidence_refs == []

    # The public decision-dispatch path must classify the same storage failure as
    # persistence rather than as an implementation defect.
    rt.step_once()
    assert rt.state.failures[-1]["kind"] == "persistence_error"
    assert rt.state.failures[-1]["target"] == "retrieval"


def test_successful_batch_commits_items_snapshot_and_refs_together(tmp_path):
    rt = runtime(
        tmp_path,
        "atomic-success",
        items=[source("a", "needle one"), source("b", "needle two")],
    )
    item_ids = rt._handle_retrieval_request("needle")
    assert len(item_ids) == 2
    assert set(item_ids) == set(rt.state.retrieval.items)
    assert len(rt.state.retrieval.results) == 1
    assert rt.state.retrieval.current_item_ids == item_ids
    assert len(rt.state.artifacts) == 2
    assert rt.state.artifacts == rt.state.evidence_refs
    assert rt.metrics["retrieval_items_admitted"] == 2
    assert rt.metrics["retrieval_requests"] == 1
    assert rt.metrics["retrieval_results"] == 2


def test_multiword_explicit_query_preserves_resume_contract(tmp_path):
    decisions = [
        Decision("retrieve", {"query": "  NEEDLE   extra  "}),
        Decision("complete", {"reason": "done"}),
    ]
    rt = runtime(
        tmp_path,
        "multiword-resume",
        items=[source("a", "needle extra")],
        controller=ScriptedController(decisions),
    )
    rt.step_once()
    rt._persist_state("test.stage8.multiword")
    before = canonical_hash(rt.state.retrieval.dump())

    resumed = runtime(
        tmp_path,
        "multiword-resume",
        items=[source("a", "needle extra")],
        controller=ScriptedController(decisions),
        resume=True,
    )
    assert canonical_hash(resumed.state.retrieval.dump()) == before
    assert resumed.state.retrieval.results[0].request.query == "NEEDLE extra"
    assert resumed.state.retrieval.results[0].request.normalized_query == "NEEDLE extra"
