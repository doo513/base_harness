from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.controller import Decision, ScriptedController
from harness.core.storage import IntegrityError, ResumeConflict, canonical_hash

from stage8_probe_support import gateway, runtime, source


def scripted():
    return ScriptedController([
        Decision("retrieve", {"query": "needle"}),
        Decision("complete", {"reason": "done"}),
    ])


def main() -> int:
    outcomes = {}
    with tempfile.TemporaryDirectory(prefix="vsh-stage8-resume-") as tmp:
        root = Path(tmp)

        base_gateway = gateway([source("a", "needle stable")], index_revision="index-v1")
        rt = runtime(
            root,
            "same",
            retrieval_gateway=base_gateway,
            controller=scripted(),
            task_revision="stage8-resume-probe-v1",
        )
        rt.step_once()
        rt._persist_state("probe.retrieval")
        before_state = canonical_hash(rt.state.snapshot())
        before_context = canonical_hash(rt._context())
        before_ids = list(rt.state.retrieval.current_item_ids)

        resumed = runtime(
            root,
            "same",
            retrieval_gateway=gateway([source("a", "needle stable")], index_revision="index-v1"),
            controller=scripted(),
            resume=True,
            task_revision="stage8-resume-probe-v1",
        )
        outcomes["exact_snapshot_and_projection_resume"] = {
            "passed": canonical_hash(resumed.state.snapshot()) == before_state
            and canonical_hash(resumed._context()) == before_context
            and resumed.state.retrieval.current_item_ids == before_ids,
            "item_count": len(before_ids),
        }

        drift_blocked = False
        try:
            runtime(
                root,
                "same",
                retrieval_gateway=gateway([source("a", "needle stable")], index_revision="index-v2"),
                controller=scripted(),
                resume=True,
                task_revision="stage8-resume-probe-v1",
            )
        except ResumeConflict:
            drift_blocked = True
        outcomes["provider_index_drift_fails_closed"] = {
            "passed": drift_blocked,
        }

        tamper = runtime(
            root,
            "tamper",
            retrieval_gateway=gateway([source("a", "needle stable")]),
            controller=scripted(),
            task_revision="stage8-tamper-probe-v1",
        )
        tamper.step_once()
        tamper._persist_state("probe.retrieval")
        item_id = tamper.state.retrieval.current_item_ids[0]
        artifact_path = tamper.artifacts.resolve(tamper.state.retrieval.items[item_id].content_ref)
        artifact_path.write_text("tampered", encoding="utf-8")
        tamper_blocked = False
        try:
            runtime(
                root,
                "tamper",
                retrieval_gateway=gateway([source("a", "needle stable")]),
                controller=scripted(),
                resume=True,
                task_revision="stage8-tamper-probe-v1",
            )
        except IntegrityError:
            tamper_blocked = True
        outcomes["tampered_artifact_fails_resume"] = {
            "passed": tamper_blocked,
        }

        missing = runtime(
            root,
            "missing",
            retrieval_gateway=gateway([source("a", "needle stable")]),
            controller=scripted(),
            task_revision="stage8-missing-probe-v1",
        )
        missing.step_once()
        missing._persist_state("probe.retrieval")
        item_id = missing.state.retrieval.current_item_ids[0]
        missing.artifacts.resolve(missing.state.retrieval.items[item_id].content_ref).unlink()
        missing_blocked = False
        try:
            runtime(
                root,
                "missing",
                retrieval_gateway=gateway([source("a", "needle stable")]),
                controller=scripted(),
                resume=True,
                task_revision="stage8-missing-probe-v1",
            )
        except IntegrityError:
            missing_blocked = True
        outcomes["missing_artifact_fails_resume"] = {
            "passed": missing_blocked,
        }

    summary = {
        "all_passed": all(item["passed"] for item in outcomes.values()),
        "scenario_count": len(outcomes),
        "resume_divergence": 0 if outcomes["exact_snapshot_and_projection_resume"]["passed"] else 1,
        "drift_acceptances": 0 if outcomes["provider_index_drift_fails_closed"]["passed"] else 1,
        "tamper_acceptances": 0 if outcomes["tampered_artifact_fails_resume"]["passed"] else 1,
    }
    print(json.dumps({
        "stage": "08",
        "probe": "retrieval-resume-rc1",
        "outcomes": outcomes,
        "summary": summary,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
