from __future__ import annotations

from harness.core.budget import Budget
from harness.core.controller import Decision, ScriptedController
from harness.core.runtime import HarnessRuntime
from harness.core.state import Authority, Claim, ClaimStatus, HarnessState, Observation
from harness.core.storage import canonical_json
from harness.core.tools import ToolResult
from harness.profiles.software import SoftwareProfile


def _runtime(tmp_path, name="audit"):
    workspace = tmp_path / f"{name}-workspace"
    workspace.mkdir()
    profile = SoftwareProfile(workspace=workspace, acceptance_commands=["false"])
    return HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=tmp_path / f"{name}-run",
        workspace=workspace,
        budget=Budget(hard_max_steps=8),
    )


def _register_evidence(runtime, *, name: str, content: str, step: int, source: str = "shell") -> str:
    ref = runtime.artifacts.put_text(name, content)
    runtime.state.artifacts.append(ref)
    runtime.state.evidence_refs.append(ref)
    runtime.state.observations.append(
        Observation(step=step, source=source, ok=True, preview=content, artifact_ref=ref)
    )
    return ref


def test_refuted_hypothesis_repackaged_same_content_is_not_new_evidence(tmp_path):
    runtime = _runtime(tmp_path, "same-content")
    first = _register_evidence(runtime, name="first.txt", content="same bytes", step=0)
    repackaged = _register_evidence(runtime, name="second.txt", content="same bytes", step=1)
    assert first != repackaged

    runtime.state.refuted_hypotheses["h"] = Claim(
        "h",
        1,
        status=ClaimStatus.REFUTED,
        evidence_refs=[first],
    )
    runtime._dispatch_decision(Decision("propose", {
        "key": "h",
        "value": 1,
        "evidence_refs": [repackaged],
    }))

    assert "h" not in runtime.state.hypotheses
    assert any(item["kind"] == "hypothesis_refuted" for item in runtime.state.failures)


def test_refuted_hypothesis_content_delta_from_same_source_can_reopen(tmp_path):
    runtime = _runtime(tmp_path, "content-delta")
    first = _register_evidence(runtime, name="first.txt", content="old bytes", step=0)
    changed = _register_evidence(runtime, name="second.txt", content="new bytes", step=1)

    runtime.state.refuted_hypotheses["h"] = Claim(
        "h",
        1,
        status=ClaimStatus.REFUTED,
        evidence_refs=[first],
    )
    runtime._dispatch_decision(Decision("propose", {
        "key": "h",
        "value": 2,
        "evidence_refs": [changed],
    }))

    assert runtime.state.hypotheses["h"].value == 2


def test_verified_commit_clears_current_refuted_marker_for_same_key():
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

    assert state.facts["fact.x"].value == "new"
    assert "fact.x" not in state.refuted_hypotheses


def test_large_structured_tool_output_is_artifact_full_state_preview_bounded(tmp_path):
    runtime = _runtime(tmp_path, "large-observation")
    output = {"payload": ["x" * 2000 for _ in range(20)]}
    full_chars = len(canonical_json(output))
    assert full_chars > runtime.OBSERVATION_PREVIEW_MAX_CHARS

    observation = runtime._store_tool_observation(
        "huge",
        ToolResult(True, output=output, error="E" * 10_000),
    )
    persisted_preview_chars = len(canonical_json(observation.preview))

    assert persisted_preview_chars <= runtime.OBSERVATION_PREVIEW_MAX_CHARS
    assert observation.error is not None
    assert len(observation.error) <= runtime.OBSERVATION_ERROR_MAX_CHARS
    assert isinstance(observation.preview, dict)
    assert observation.preview["truncated"] is True
    assert observation.preview["full_output"] == "artifact_ref"

    artifact = runtime.artifacts.verified_read_json(observation.artifact_ref)
    assert artifact["output"] == output
    assert artifact["error"] == "E" * 10_000
