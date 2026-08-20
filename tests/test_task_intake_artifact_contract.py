from pathlib import Path

from harness.core.state import HarnessState, Observation
from harness.profiles.software import SoftwareProfile
from harness.task_contracts import EvidenceArtifactTaskProfile, EvidenceBackedArtifactOracle
from harness.task_intake import analyze_task_input, detect_requested_workspace


def test_task_intake_uses_one_explicit_existing_workspace(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    task = f'"{project}" 분석해서 딥한 보고서 써줘'
    intake = analyze_task_input(task)
    assert Path(intake.requested_workspace) == project.resolve()
    assert intake.workspace_ambiguous is False
    assert intake.artifact_target == "PROJECT_ANALYSIS_REPORT.md"
    assert intake.evidence_backed_artifact is True


def test_task_intake_does_not_choose_between_multiple_existing_workspaces(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    workspace, ambiguous = detect_requested_workspace(f'compare "{first}" and "{second}"')
    assert workspace is None
    assert ambiguous is True


def test_task_intake_preserves_explicit_markdown_deliverable(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    intake = analyze_task_input(f'"{project}" 분석해서 deep_architecture.md 보고서 작성')
    assert intake.artifact_target == "deep_architecture.md"


def _evidence_state():
    state = HarnessState()
    state.observations.extend([
        Observation(step=0, source="directory.list", ok=True, artifact_ref="artifact:list"),
        Observation(step=1, source="file.read", ok=True, artifact_ref="artifact:read"),
    ])
    state.evidence_refs.extend(["artifact:list", "artifact:read"])
    return state


def test_evidence_backed_artifact_oracle_requires_workspace_evidence(tmp_path):
    report = tmp_path / "PROJECT_ANALYSIS_REPORT.md"
    report.write_text("# Report\n" + "evidence based content\n" * 30, encoding="utf-8")
    oracle = EvidenceBackedArtifactOracle("PROJECT_ANALYSIS_REPORT.md")
    result = oracle.evaluate(goal=None, state=HarnessState(), workspace=tmp_path)
    assert result.accepted is False
    assert "insufficient workspace evidence" in result.reason


def test_evidence_backed_artifact_oracle_accepts_report_after_inspection(tmp_path):
    report = tmp_path / "PROJECT_ANALYSIS_REPORT.md"
    report.write_text("# Report\n" + "evidence based content\n" * 30, encoding="utf-8")
    oracle = EvidenceBackedArtifactOracle("PROJECT_ANALYSIS_REPORT.md")
    result = oracle.evaluate(goal=None, state=_evidence_state(), workspace=tmp_path)
    assert result.accepted is True
    assert result.coverage["workspace_evidence"] == 2
    assert result.coverage["file_reads"] == 1


def test_artifact_task_overlay_keeps_base_profile_identity_and_changes_workflow(tmp_path):
    base = SoftwareProfile(workspace=tmp_path)
    profile = EvidenceArtifactTaskProfile(base, artifact_target="PROJECT_ANALYSIS_REPORT.md")
    assert profile.name == "software"
    assert profile.workflow_contract().name == "evidence-backed-artifact"
    goal = profile.default_goal()
    assert "PROJECT_ANALYSIS_REPORT.md" in " ".join(goal.acceptance)
    assert any("checklist" in item for item in goal.constraints)
