from harness.core.claim_contracts import ClaimContractRegistry, ClaimContractRule
from harness.core.controller import ScriptedController
from harness.core.state import Claim, Authority
from harness.core.verification import VerificationContract, VerificationLevel
from harness.core.runtime import HarnessRuntime
from harness.profiles.ctf import CTFProfile
from harness.profiles.software import SoftwareProfile


def assertion(expected=0):
    return {
        "kind": "artifact_json_assertion",
        "path": ["output", "returncode"],
        "operator": "eq",
        "expected": expected,
    }


def test_claim_registry_uses_longest_prefix_and_fails_unknown():
    legacy = VerificationContract.legacy(VerificationLevel.SCHEMA)
    registry = ClaimContractRegistry((
        ClaimContractRule("broad", "artifact_", legacy, ("exists",)),
        ClaimContractRule("specific", "artifact_assertion.", legacy, ("exists",)),
    ))
    assert registry.resolve("artifact_assertion.x").claim_class == "specific"
    assert registry.resolve("other.x") is None


def test_software_unknown_claim_class_cannot_commit(tmp_path):
    profile = SoftwareProfile(workspace=tmp_path, acceptance_commands=["false"])
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=tmp_path / "run",
        workspace=tmp_path,
    )
    ref = runtime.artifacts.put_json("evidence.json", {"ok": True, "output": {"returncode": 0}})
    runtime.state.artifacts.append(ref)
    runtime.state.evidence_refs.append(ref)
    runtime.state.propose(Claim("security.sql_injection_success", assertion(), evidence_refs=[ref]))

    runtime._verify_claim("security.sql_injection_success")

    assert "security.sql_injection_success" not in runtime.state.facts
    assert runtime.state.failures[-1]["kind"] == "verification_failed"
    assert "unknown claim class" in runtime.state.failures[-1]["message"]


def test_software_declared_artifact_claim_class_commits(tmp_path):
    profile = SoftwareProfile(workspace=tmp_path, acceptance_commands=["false"])
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=tmp_path / "run",
        workspace=tmp_path,
    )
    ref = runtime.artifacts.put_json("evidence.json", {"ok": True, "output": {"returncode": 0}})
    runtime.state.artifacts.append(ref)
    runtime.state.evidence_refs.append(ref)
    key = "artifact_assertion.build_returncode"
    runtime.state.propose(Claim(key, assertion(), evidence_refs=[ref]))

    runtime._verify_claim(key)

    assert runtime.state.facts[key].authority == Authority.ENVIRONMENT


def test_ctf_catchall_class_is_explicitly_supported_only(tmp_path):
    profile = CTFProfile(workspace=tmp_path)
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=tmp_path / "run",
        workspace=tmp_path,
    )
    ref = runtime.artifacts.put_json("evidence.json", {"observed": "offset=72"})
    runtime.state.artifacts.append(ref)
    runtime.state.evidence_refs.append(ref)
    key = "offset"
    runtime.state.propose(Claim(key, 72, evidence_refs=[ref]))

    runtime._verify_claim(key)

    assert runtime.state.facts[key].authority == Authority.SUPPORTED
    assert profile.claim_verification_registry().resolve(key).claim_class == "ctf.intermediate_supported"
