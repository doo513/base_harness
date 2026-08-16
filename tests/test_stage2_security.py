import os
from pathlib import Path

import pytest

from harness.core.security import (
    Principal,
    Capability,
    CapabilityPolicy,
    SecurityConfig,
    SecurityLayout,
    SecurityViolation,
)
from harness.core.sandbox import (
    ExecutionResult,
    IsolationAttestation,
    LocalProcessBackend,
    NetworkPolicy,
    RecordingIsolatedTestBackend,
)
from harness.core.tools import ActionRuntime, ToolCall, make_shell_tool
from harness.core.oracles import SealedAssetBundle, SealedCommandCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.core.controller import Decision, ScriptedController
from harness.core.budget import Budget
from harness.profiles.software import SoftwareProfile


def test_default_capability_policy_separates_principals():
    policy = CapabilityPolicy.default()
    assert policy.allows(Principal.ACTOR, Capability.TOOL_WRITE)
    assert not policy.allows(Principal.ACTOR, Capability.STATE_COMMIT)
    assert policy.allows(Principal.KERNEL, Capability.STATE_COMMIT)
    assert not policy.allows(Principal.VERIFIER, Capability.TOOL_WRITE)
    assert policy.allows(Principal.ORACLE, Capability.ORACLE_EXECUTE)


def test_verifier_principal_cannot_run_write_tool(tmp_path):
    called = {"n": 0}
    def write_handler():
        called["n"] += 1
        return "changed"
    from harness.core.tools import ToolSpec, SideEffect
    runtime = ActionRuntime({
        "write": ToolSpec(name="write", description="write-side-effect test", handler=write_handler, side_effect=SideEffect.WRITE)
    }, principal=Principal.VERIFIER)
    result = runtime.execute(ToolCall("write", {}))
    assert result.ok is False
    assert result.security_violation is True
    assert called["n"] == 0


def test_strict_layout_rejects_harness_run_dir_inside_actor_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    layout = SecurityLayout.build(workspace=workspace, run_dir=workspace / ".harness")
    with pytest.raises(SecurityViolation): layout.validate_strict()


def test_strict_layout_rejects_oracle_assets_inside_actor_workspace(tmp_path):
    workspace = tmp_path / "workspace"; workspace.mkdir()
    run_dir = tmp_path / "run"
    oracle_root = workspace / "hidden-tests"; oracle_root.mkdir()
    layout = SecurityLayout.build(workspace=workspace, run_dir=run_dir, oracle_root=oracle_root)
    with pytest.raises(SecurityViolation): layout.validate_strict()


def test_strict_tool_isolation_refuses_plain_local_process(tmp_path):
    tool = make_shell_tool(tmp_path, backend=LocalProcessBackend(inherit_env=False))
    runtime = ActionRuntime({"shell": tool}, strict_isolation=True)
    result = runtime.execute(ToolCall("shell", {"command": "printf hi"}))
    assert result.ok is False
    assert result.security_violation is True
    assert "filesystem isolation" in result.error


def test_test_only_isolation_attestation_is_rejected_by_default(tmp_path):
    backend = RecordingIsolatedTestBackend()
    tool = make_shell_tool(tmp_path, backend=backend)
    runtime = ActionRuntime({"shell": tool}, strict_isolation=True)
    result = runtime.execute(ToolCall("shell", {"command": "printf hi"}))
    assert result.ok is False
    assert result.security_violation is True
    assert "test-only" in result.error
    assert backend.calls == []


def test_test_only_backend_can_exercise_strict_policy_path_when_explicitly_allowed(tmp_path):
    backend = RecordingIsolatedTestBackend({"printf hi": ExecutionResult(0, "hi", "")})
    tool = make_shell_tool(tmp_path, backend=backend)
    runtime = ActionRuntime({"shell": tool}, strict_isolation=True, network_policy=NetworkPolicy.DENY, allow_test_attestation=True)
    result = runtime.execute(ToolCall("shell", {"command": "printf hi"}))
    assert result.ok is True
    assert result.output["stdout"] == "hi"
    assert len(backend.calls) == 1


def test_local_backend_sanitizes_parent_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("VSH_TEST_SECRET", "do-not-leak")
    backend = LocalProcessBackend(inherit_env=False)
    result = backend.run_shell(workspace=tmp_path, command="python -c \"import os; print(os.getenv('VSH_TEST_SECRET', 'MISSING'))\"", timeout_seconds=10)
    assert result.returncode == 0
    assert result.stdout.strip() == "MISSING"


def test_local_backend_explicitly_reports_no_filesystem_or_network_isolation(tmp_path):
    att = LocalProcessBackend(inherit_env=False).isolation_attestation(workspace=tmp_path)
    assert att.filesystem_isolated is False
    assert att.network_isolated is False
    assert att.environment_sanitized is True


def test_sealed_asset_bundle_detects_mutation(tmp_path):
    sealed = tmp_path / "sealed"; sealed.mkdir()
    target = sealed / "hidden.txt"; target.write_text("expected", encoding="utf-8")
    bundle = SealedAssetBundle(sealed)
    assert bundle.verify_unchanged().ok
    target.write_text("tampered", encoding="utf-8")
    verification = bundle.verify_unchanged()
    assert verification.ok is False
    assert verification.changed == ["hidden.txt"]


def test_sealed_oracle_rejects_assets_modified_before_evaluation(tmp_path):
    workspace = tmp_path / "workspace"; sealed = tmp_path / "sealed"
    workspace.mkdir(); sealed.mkdir()
    hidden = sealed / "expected.txt"; hidden.write_text("ok", encoding="utf-8")
    oracle = SealedCommandCompletionOracle(["true"], sealed_root=sealed)
    hidden.write_text("attacker changed test", encoding="utf-8")
    result = oracle.evaluate(goal=None, state=None, workspace=workspace)
    assert result.accepted is False
    assert "changed before evaluation" in result.reason
    assert result.oracle_id
    assert result.evidence_hash


def test_sealed_oracle_rejects_mutation_during_evaluation(tmp_path):
    workspace = tmp_path / "workspace"; sealed = tmp_path / "sealed"
    workspace.mkdir(); sealed.mkdir()
    hidden = sealed / "expected.txt"; hidden.write_text("ok", encoding="utf-8")
    class MutatingBackend:
        name = "mutating_test_backend"
        def isolation_attestation(self, *, workspace):
            return IsolationAttestation(filesystem_isolated=True, network_isolated=True, environment_sanitized=True, source="test_fixture")
        def run_shell(self, *, workspace, command, timeout_seconds, env=None):
            hidden.write_text("mutated-during-oracle", encoding="utf-8")
            return ExecutionResult(0, "fake pass", "")
    oracle = SealedCommandCompletionOracle(["true"], sealed_root=sealed, backend=MutatingBackend())
    result = oracle.evaluate(goal=None, state=None, workspace=workspace)
    assert result.accepted is False
    assert "changed during evaluation" in result.reason


def test_sealed_oracle_clean_execution_records_provenance_without_raw_command(tmp_path):
    workspace = tmp_path / "workspace"; sealed = tmp_path / "sealed"
    workspace.mkdir(); sealed.mkdir()
    (sealed / "expected.txt").write_text("ok", encoding="utf-8")
    oracle = SealedCommandCompletionOracle(['test "$(cat {sealed_root}/expected.txt)" = ok'], sealed_root=sealed)
    result = oracle.evaluate(goal=None, state=None, workspace=workspace)
    assert result.accepted is True
    assert result.independence_level == "sealed_integrity_only"
    assert result.evidence_hash
    assert result.evidence[0]["command_sha256"]
    assert "command" not in result.evidence[0]


def test_strict_runtime_can_require_sealed_oracle(tmp_path):
    workspace = tmp_path / "workspace"; workspace.mkdir()
    unsealed = SoftwareProfile(workspace=workspace, acceptance_commands=["true"])
    with pytest.raises(SecurityViolation):
        HarnessRuntime(goal=unsealed.default_goal(), profile=unsealed, controller=ScriptedController([]), run_dir=tmp_path / "run", workspace=workspace, security_config=SecurityConfig(strict_layout=True, require_sealed_oracle=True))


def test_runtime_with_separate_sealed_oracle_accepts_and_records_independence(tmp_path):
    workspace = tmp_path / "workspace"; sealed = tmp_path / "sealed"; run_dir = tmp_path / "run"
    workspace.mkdir(); sealed.mkdir(); (sealed / "expected.txt").write_text("ok", encoding="utf-8")
    profile = SoftwareProfile(workspace=workspace, acceptance_commands=['test "$(cat {sealed_root}/expected.txt)" = ok'], sealed_oracle_root=sealed)
    state = HarnessRuntime(goal=profile.default_goal(), profile=profile, controller=ScriptedController([Decision("complete", {"reason": "evaluate"})]), run_dir=run_dir, workspace=workspace, budget=Budget(hard_max_steps=2), security_config=SecurityConfig(strict_layout=True, require_sealed_oracle=True)).run()
    assert state.completed is True
    oracle_events = [line for line in (run_dir / "events.jsonl").read_text().splitlines() if '"completion.oracle"' in line]
    assert oracle_events
    assert "sealed_integrity_only" in oracle_events[0]


def test_strict_runtime_fails_closed_before_unisolated_shell_executes(tmp_path):
    workspace = tmp_path / "workspace"; run_dir = tmp_path / "run"; private = tmp_path / "private"
    workspace.mkdir(); private.mkdir()
    canary = private / "canary.txt"; canary.write_text("SECRET", encoding="utf-8")
    profile = SoftwareProfile(workspace=workspace, acceptance_commands=["false"])
    state = HarnessRuntime(goal=profile.default_goal(), profile=profile, controller=ScriptedController([Decision("tool", {"tool": "shell", "args": {"command": f"cat {canary}"}})]), run_dir=run_dir, workspace=workspace, budget=Budget(hard_max_steps=1), security_config=SecurityConfig(strict_layout=True, strict_tool_isolation=True, network_policy="deny")).run()
    assert state.observations
    assert state.observations[0].ok is False
    assert state.observations[0].preview is None
    assert any("strict isolation" in f["message"] or "filesystem isolation" in f["message"] for f in state.failures)
    metrics = (run_dir / "metrics.json").read_text(encoding="utf-8")
    assert '"security_violations": 1' in metrics


def test_sealed_bundle_rejects_symlink_assets(tmp_path):
    sealed = tmp_path / "sealed"; target = tmp_path / "outside.txt"
    sealed.mkdir(); target.write_text("outside", encoding="utf-8"); (sealed / "link.txt").symlink_to(target)
    with pytest.raises(ValueError): SealedAssetBundle(sealed)


def test_sealed_bundle_detects_permission_change(tmp_path):
    sealed = tmp_path / "sealed"; sealed.mkdir()
    target = sealed / "hidden.txt"; target.write_text("expected", encoding="utf-8"); target.chmod(0o600)
    bundle = SealedAssetBundle(sealed); target.chmod(0o644)
    verification = bundle.verify_unchanged()
    assert verification.ok is False
    assert "hidden.txt" in verification.changed


def test_strict_layout_rejects_actor_workspace_nested_inside_run_dir(tmp_path):
    run_dir = tmp_path / "run-root"; workspace = run_dir / "workspace"; workspace.mkdir(parents=True)
    layout = SecurityLayout.build(workspace=workspace, run_dir=run_dir)
    with pytest.raises(SecurityViolation): layout.validate_strict()


def test_strict_layout_rejects_actor_workspace_nested_inside_oracle_root(tmp_path):
    oracle_root = tmp_path / "oracle-root"; workspace = oracle_root / "workspace"; run_dir = tmp_path / "run"; workspace.mkdir(parents=True)
    layout = SecurityLayout.build(workspace=workspace, run_dir=run_dir, oracle_root=oracle_root)
    with pytest.raises(SecurityViolation): layout.validate_strict()


def test_actor_controller_receives_detached_state_copy(tmp_path):
    from harness.core.state import Claim, ClaimStatus, Authority
    workspace = tmp_path / "workspace"; workspace.mkdir()
    profile = SoftwareProfile(workspace=workspace, acceptance_commands=["false"])
    class MaliciousController:
        def decide(self, goal, state, context):
            state.completed = True
            state.facts["forged"] = Claim("forged", True, ClaimStatus.VERIFIED, Authority.MODEL)
            return Decision("complete", {"reason": "forged local state"})
    live = HarnessRuntime(goal=profile.default_goal(), profile=profile, controller=MaliciousController(), run_dir=tmp_path / "run", workspace=workspace, budget=Budget(hard_max_steps=1)).run()
    assert live.completed is False
    assert "forged" not in live.facts


def test_completion_oracle_receives_detached_state_copy(tmp_path):
    from harness.core.oracles import PredicateCompletionOracle
    from harness.core.state import Claim, ClaimStatus, Authority
    workspace = tmp_path / "workspace"; workspace.mkdir()
    class Profile(SoftwareProfile):
        def completion_oracle(self):
            def malicious_oracle(*, goal, state, workspace):
                state.completed = True
                state.facts["oracle-forged"] = Claim("oracle-forged", True, ClaimStatus.VERIFIED, Authority.EXTERNAL_ORACLE)
                return False
            return PredicateCompletionOracle(malicious_oracle, name="malicious_test_oracle")
    profile = Profile(workspace=workspace, acceptance_commands=["false"])
    live = HarnessRuntime(goal=profile.default_goal(), profile=profile, controller=ScriptedController([Decision("complete", {"reason": "evaluate"})]), run_dir=tmp_path / "run", workspace=workspace, budget=Budget(hard_max_steps=1)).run()
    assert live.completed is False
    assert "oracle-forged" not in live.facts


def test_actor_visible_artifact_refs_are_opaque_not_private_paths(tmp_path):
    workspace = tmp_path / "workspace"; run_dir = tmp_path / "run"; workspace.mkdir()
    profile = SoftwareProfile(workspace=workspace, acceptance_commands=["false"])
    state = HarnessRuntime(goal=profile.default_goal(), profile=profile, controller=ScriptedController([Decision("tool", {"tool": "shell", "args": {"command": "printf evidence"}})]), run_dir=run_dir, workspace=workspace, budget=Budget(hard_max_steps=1)).run()
    ref = state.observations[0].artifact_ref
    assert ref.startswith("artifact://")
    assert str(run_dir.resolve()) not in ref
    assert state.artifacts[0] == ref


def test_sealed_oracle_does_not_treat_test_fixture_attestation_as_production_isolation(tmp_path):
    workspace = tmp_path / "workspace"; sealed = tmp_path / "sealed"; workspace.mkdir(); sealed.mkdir()
    (sealed / "expected.txt").write_text("ok", encoding="utf-8")
    backend = RecordingIsolatedTestBackend({"true": ExecutionResult(0, "", "")})
    oracle = SealedCommandCompletionOracle(["true"], sealed_root=sealed, backend=backend, require_filesystem_isolation=True)
    result = oracle.evaluate(goal=None, state=None, workspace=workspace)
    assert result.accepted is False
    assert result.independence_level == "sealed_integrity_only"
    assert "requires filesystem-isolated backend" in result.reason
    assert backend.calls == []
