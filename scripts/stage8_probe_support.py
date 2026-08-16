from __future__ import annotations

from pathlib import Path
from typing import Iterable

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision, ScriptedController
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.retrieval import LocalLexicalRetrievalGateway, RetrievalPolicy, RetrievalSourceItem
from harness.core.runtime import HarnessRuntime
from harness.profiles.base import DomainProfile


class Stage8ProbeProfile(DomainProfile):
    name = "stage8-retrieval-probe"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def default_goal(self):
        return GoalContract(
            goal="prove retrieval remains untrusted bounded evidence",
            acceptance=["completion remains oracle-owned"],
            constraints=["retrieval cannot directly write verified facts"],
            pinned_constraints=["retrieval instruction authority is none"],
            task_id="stage8-retrieval-probe",
        )

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(True, "probe complete"),
            name="stage8-probe-oracle",
        )


def source(
    source_id: str,
    content: str,
    *,
    revision: str = "r1",
    locator: str | None = None,
    metadata=None,
    scope: str = "project",
) -> RetrievalSourceItem:
    return RetrievalSourceItem(
        source_id=source_id,
        source_revision=revision,
        source_locator=locator or source_id,
        content=content,
        scope=scope,
        metadata=dict(metadata or {}),
    )


def gateway(items: Iterable[RetrievalSourceItem], *, index_revision: str = "index-v1"):
    return LocalLexicalRetrievalGateway(items, index_revision=index_revision)


def runtime(
    root: Path,
    name: str,
    *,
    retrieval_gateway,
    retrieval_policy: RetrievalPolicy | None = None,
    controller=None,
    resume: bool = False,
    task_revision: str | None = None,
):
    workspace = root / f"{name}-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    profile = Stage8ProbeProfile(workspace)
    kwargs = dict(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller or ScriptedController([Decision("complete", {"reason": "done"})]),
        run_dir=root / name,
        workspace=workspace,
        retrieval_gateway=retrieval_gateway,
        retrieval_policy=retrieval_policy or RetrievalPolicy(enabled=True),
        budget=Budget(hard_max_steps=20),
        task_revision=task_revision or f"stage8-{name}-v1",
    )
    return HarnessRuntime.resume(**kwargs) if resume else HarnessRuntime(**kwargs)
