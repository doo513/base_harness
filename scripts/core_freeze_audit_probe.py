from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.budget import Budget
from harness.core.controller import Decision, ScriptedController
from harness.core.runtime import HarnessRuntime
from harness.core.state import Authority, Claim, ClaimStatus, HarnessState, Observation
from harness.core.storage import canonical_json
from harness.core.tools import ToolResult
from harness.profiles.software import SoftwareProfile


def _runtime(root: Path, name: str) -> HarnessRuntime:
    workspace = root / f"{name}-workspace"
    workspace.mkdir()
    profile = SoftwareProfile(workspace=workspace, acceptance_commands=["false"])
    return HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=root / f"{name}-run",
        workspace=workspace,
        budget=Budget(hard_max_steps=8),
    )


def _register(runtime: HarnessRuntime, name: str, content: str, step: int) -> str:
    ref = runtime.artifacts.put_text(name, content)
    runtime.state.artifacts.append(ref)
    runtime.state.evidence_refs.append(ref)
    runtime.state.observations.append(
        Observation(step=step, source="shell", ok=True, preview=content, artifact_ref=ref)
    )
    return ref


def main() -> None:
    outcomes = {}
    metrics = {}
    with tempfile.TemporaryDirectory(prefix="vsh-core-freeze-") as tmp:
        root = Path(tmp)

        same = _runtime(root, "same")
        first = _register(same, "first.txt", "same bytes", 0)
        repackaged = _register(same, "second.txt", "same bytes", 1)
        same.state.refuted_hypotheses["h"] = Claim(
            "h", 1, status=ClaimStatus.REFUTED, evidence_refs=[first]
        )
        same._dispatch_decision(Decision("propose", {
            "key": "h",
            "value": 1,
            "evidence_refs": [repackaged],
        }))
        outcomes["same_content_new_ref_not_novel"] = {
            "passed": (
                first != repackaged
                and "h" not in same.state.hypotheses
                and any(item["kind"] == "hypothesis_refuted" for item in same.state.failures)
            ),
            "ref_strings_differ": first != repackaged,
        }

        changed = _runtime(root, "changed")
        old = _register(changed, "old.txt", "old bytes", 0)
        new = _register(changed, "new.txt", "new bytes", 1)
        changed.state.refuted_hypotheses["h"] = Claim(
            "h", 1, status=ClaimStatus.REFUTED, evidence_refs=[old]
        )
        changed._dispatch_decision(Decision("propose", {
            "key": "h",
            "value": 2,
            "evidence_refs": [new],
        }))
        outcomes["content_delta_can_reopen"] = {
            "passed": changed.state.hypotheses.get("h") is not None,
        }

        state = HarnessState()
        state.refuted_hypotheses["fact.x"] = Claim(
            "fact.x", "old", status=ClaimStatus.REFUTED
        )
        state.commit_verified(Claim(
            "fact.x",
            "new",
            status=ClaimStatus.VERIFIED,
            authority=Authority.ENVIRONMENT,
        ))
        outcomes["verified_commit_clears_stale_refuted_marker"] = {
            "passed": "fact.x" in state.facts and "fact.x" not in state.refuted_hypotheses,
        }

        large = _runtime(root, "large")
        output = {"payload": ["x" * 2000 for _ in range(20)]}
        full_chars = len(canonical_json(output))
        observation = large._store_tool_observation(
            "huge",
            ToolResult(True, output=output, error="E" * 10_000),
        )
        preview_chars = len(canonical_json(observation.preview))
        artifact = large.artifacts.verified_read_json(observation.artifact_ref)
        outcomes["durable_observation_preview_bounded"] = {
            "passed": (
                preview_chars <= large.OBSERVATION_PREVIEW_MAX_CHARS
                and artifact["output"] == output
                and len(observation.error or "") <= large.OBSERVATION_ERROR_MAX_CHARS
            ),
        }
        metrics["structured_output_full_chars"] = full_chars
        metrics["durable_preview_chars"] = preview_chars
        metrics["preview_reduction_fraction"] = round(1.0 - (preview_chars / full_chars), 6)

    all_passed = all(item["passed"] for item in outcomes.values())
    report = {
        "track": "core-freeze-audit",
        "probe": "post-stage08-core-freeze-v1",
        "outcomes": outcomes,
        "metrics": metrics,
        "summary": {
            "scenario_count": len(outcomes),
            "all_passed": all_passed,
            "new_stage_created": False,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if not all_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
