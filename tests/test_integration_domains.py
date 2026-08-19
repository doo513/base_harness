from harness.core.controller import ScriptedController
from harness.core.runtime import HarnessRuntime
from harness.core.state import Claim, ClaimStatus, Authority, HarnessState
from harness.core.storage import ArtifactStore
from harness.profiles.hackathon import HackathonProfile
from harness.profiles.hackathon_verification import HackathonDemoCheckVerifier
from harness.profiles.software import SoftwareProfile


def _verified(key, value):
    return Claim(key, value, status=ClaimStatus.VERIFIED, authority=Authority.ENVIRONMENT)


def test_software_domain_progress_uses_verified_facts_only(tmp_path):
    profile = SoftwareProfile(workspace=tmp_path, acceptance_commands=["false"])
    state = HarnessState()
    state.propose(Claim("software.build_result.guess", {"succeeded": True}))
    assert profile.task_progress_snapshot(goal=profile.default_goal(), state=state) == {
        "milestones": [], "score": 0.0
    }

    state.facts["software.build_result.real"] = _verified(
        "software.build_result.real", {"succeeded": True}
    )
    state.facts["software.test_result.real"] = _verified(
        "software.test_result.real", {"succeeded": True}
    )
    snapshot = profile.task_progress_snapshot(goal=profile.default_goal(), state=state)
    assert snapshot["milestones"] == ["build_passed", "tests_passed"]
    assert snapshot["score"] == 2.0


def test_hackathon_execution_check_verifier_binds_boolean_claim_to_execution_artifact(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    ref = store.put_json("demo.json", {
        "ok": True,
        "output": {"returncode": 0, "stdout": "demo ok", "stderr": "", "timed_out": False},
        "error": None,
    })
    verifier = HackathonDemoCheckVerifier()
    result = verifier.verify(
        {"succeeded": True},
        {
            "claim_evidence_refs": [ref],
            "artifact_root": str(store.root),
            "claim_key": "hackathon.demo_check.primary",
            "claim_class": "hackathon.demo_check",
        },
    )
    assert result.verified is True
    assert result.coverage == ["hackathon_demo_execution"] or result.coverage == ("hackathon_demo_execution",)


def test_hackathon_progress_and_soft_evaluation_are_separate(tmp_path):
    profile = HackathonProfile(workspace=tmp_path, acceptance_commands=["false"])
    state = HarnessState()
    state.facts["hackathon.demo_check.primary"] = _verified(
        "hackathon.demo_check.primary", {"succeeded": True}
    )
    snapshot = profile.task_progress_snapshot(goal=profile.default_goal(), state=state)
    assert snapshot == {"milestones": ["demo_check_passed"], "score": 1.0}
    evaluation = profile.evaluation_contract().dump()
    assert evaluation["advisory_only"] is True
    assert evaluation["progress_authority"] is False
    assert evaluation["completion_authority"] is False


def test_domain_contract_is_model_visible_without_completion_authority(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = SoftwareProfile(workspace=workspace, acceptance_commands=["false"])
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=tmp_path / "run",
        workspace=workspace,
    )
    context = runtime._context()
    assert context["domain_contract"]["profile"] == "software"
    assert context["domain_contract"]["workflow"]["name"] == "software-development"
    assert context["domain_contract"]["evaluation"]["advisory_only"] is True
    assert context["domain_contract"]["evaluation_completion_authority"] is False
    assert set(profile.tools()) >= {"shell", "argv"}
