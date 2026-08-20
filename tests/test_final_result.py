import json

from harness.core.state import Claim, ClaimStatus, Authority, HarnessState, Observation
from harness.final_result import persist_final_result


def test_final_result_records_verified_facts_evidence_and_deliverable(tmp_path):
    report = tmp_path / "PROJECT_ANALYSIS_REPORT.md"
    report.write_text("# Report\n" + "grounded finding\n" * 20, encoding="utf-8")

    state = HarnessState(step=7, completed=True)
    state.observations.append(
        Observation(step=1, source="file.read", ok=True, artifact_ref="artifact:read")
    )
    state.evidence_refs.append("artifact:read")
    state.facts["example"] = Claim(
        "example",
        {"ok": True},
        status=ClaimStatus.VERIFIED,
        authority=Authority.ENVIRONMENT,
        evidence_refs=["artifact:read"],
    )

    run_dir = tmp_path / "run"
    path = persist_final_result(
        run_dir,
        state=state,
        workspace=tmp_path,
        artifact_target="PROJECT_ANALYSIS_REPORT.md",
    )
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["completed"] is True
    assert result["artifact"]["exists"] is True
    assert result["evidence"]["workspace_observations"] == 1
    assert result["verified_facts"]["count"] == 1
