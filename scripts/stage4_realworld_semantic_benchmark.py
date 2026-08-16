from __future__ import annotations

import json
import shlex
import sys
import tempfile
from pathlib import Path

from harness.core.budget import Budget
from harness.core.controller import Decision, ScriptedController
from harness.core.runtime import HarnessRuntime
from harness.core.state import Claim
from harness.core.storage import ArtifactStore
from harness.core.tools import make_shell_tool
from harness.profiles.software import SoftwareProfile


class TimeoutSoftwareProfile(SoftwareProfile):
    def tools(self):
        return {
            "shell": make_shell_tool(
                self.workspace,
                timeout_seconds=0.05,
                backend=self.execution_backend,
            )
        }


def make_runtime(root: Path, name: str, *, timeout: bool = False) -> HarnessRuntime:
    workspace = root / f"{name}-workspace"
    workspace.mkdir()
    cls = TimeoutSoftwareProfile if timeout else SoftwareProfile
    profile = cls(
        workspace=workspace,
        acceptance_commands=[f"{shlex.quote(sys.executable)} -c 'raise SystemExit(0)'"],
    )
    return HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=root / f"{name}-run",
        workspace=workspace,
        budget=Budget(hard_max_steps=20),
        task_revision=f"stage4-realworld-{name}-v1",
    )


def execute(rt: HarnessRuntime, command: str) -> str:
    before = len(rt.state.observations)
    rt._dispatch_decision(Decision("tool", {"tool": "shell", "args": {"command": command}}))
    if len(rt.state.observations) != before + 1:
        raise RuntimeError("shell execution did not create exactly one Harness observation")
    return rt.state.observations[-1].artifact_ref


def predict(rt: HarnessRuntime, key: str, value, ref: str) -> bool:
    rt.state.propose(Claim(key, value, evidence_refs=[ref]))
    rt._verify_claim(key)
    return key in rt.state.facts


def record(outcomes: list[dict], *, case_id: str, claim_class: str, gold: bool, predicted: bool, source: str):
    outcomes.append({
        "id": case_id,
        "claim_class": claim_class,
        "gold": gold,
        "predicted": predicted,
        "pass": gold == predicted,
        "source": source,
    })


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vsh-stage4-realworld-") as td:
        root = Path(td)
        outcomes: list[dict] = []
        py = shlex.quote(sys.executable)

        # Build corpus: real Python compilation success and syntax failure.
        build_ok = make_runtime(root, "build-ok")
        (build_ok.workspace / "good.py").write_text("VALUE = 7\n", encoding="utf-8")
        ref = execute(build_ok, f"{py} -m py_compile good.py")
        record(outcomes, case_id="build_success_true", claim_class="software.build_result", gold=True,
               predicted=predict(build_ok, "software.build_result.compile", {"succeeded": True}, ref), source="python -m py_compile good.py")

        build_ok_false = make_runtime(root, "build-ok-false")
        (build_ok_false.workspace / "good.py").write_text("VALUE = 7\n", encoding="utf-8")
        ref = execute(build_ok_false, f"{py} -m py_compile good.py")
        record(outcomes, case_id="build_success_false_claim", claim_class="software.build_result", gold=False,
               predicted=predict(build_ok_false, "software.build_result.compile", {"succeeded": False}, ref), source="python -m py_compile good.py")

        build_bad = make_runtime(root, "build-bad")
        (build_bad.workspace / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
        ref = execute(build_bad, f"{py} -m py_compile bad.py")
        record(outcomes, case_id="build_failure_false", claim_class="software.build_result", gold=True,
               predicted=predict(build_bad, "software.build_result.compile", {"succeeded": False}, ref), source="python -m py_compile bad.py")

        build_bad_true = make_runtime(root, "build-bad-true")
        (build_bad_true.workspace / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
        ref = execute(build_bad_true, f"{py} -m py_compile bad.py")
        record(outcomes, case_id="build_failure_true_claim", claim_class="software.build_result", gold=False,
               predicted=predict(build_bad_true, "software.build_result.compile", {"succeeded": True}, ref), source="python -m py_compile bad.py")

        timeout_rt = make_runtime(root, "build-timeout", timeout=True)
        ref = execute(timeout_rt, f"{py} -c \"import time; time.sleep(0.25)\"")
        record(outcomes, case_id="build_timeout_true_claim", claim_class="software.build_result", gold=False,
               predicted=predict(timeout_rt, "software.build_result.timeout", {"succeeded": True}, ref), source="timed subprocess")

        # Test corpus: invoke the real locked pytest executable through the Harness shell tool.
        test_ok = make_runtime(root, "test-ok")
        (test_ok.workspace / "test_sample.py").write_text("def test_ok():\n    assert 2 + 2 == 4\n", encoding="utf-8")
        ref = execute(test_ok, f"{py} -m pytest -q test_sample.py")
        record(outcomes, case_id="test_success_true", claim_class="software.test_result", gold=True,
               predicted=predict(test_ok, "software.test_result.unit", {"succeeded": True}, ref), source="pytest passing test")

        test_ok_false = make_runtime(root, "test-ok-false")
        (test_ok_false.workspace / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        ref = execute(test_ok_false, f"{py} -m pytest -q test_sample.py")
        record(outcomes, case_id="test_success_false_claim", claim_class="software.test_result", gold=False,
               predicted=predict(test_ok_false, "software.test_result.unit", {"succeeded": False}, ref), source="pytest passing test")

        test_bad = make_runtime(root, "test-bad")
        (test_bad.workspace / "test_sample.py").write_text("def test_bad():\n    assert 2 + 2 == 5\n", encoding="utf-8")
        ref = execute(test_bad, f"{py} -m pytest -q test_sample.py")
        record(outcomes, case_id="test_failure_false", claim_class="software.test_result", gold=True,
               predicted=predict(test_bad, "software.test_result.unit", {"succeeded": False}, ref), source="pytest failing test")

        test_bad_true = make_runtime(root, "test-bad-true")
        (test_bad_true.workspace / "test_sample.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
        ref = execute(test_bad_true, f"{py} -m pytest -q test_sample.py")
        record(outcomes, case_id="test_failure_true_claim", claim_class="software.test_result", gold=False,
               predicted=predict(test_bad_true, "software.test_result.unit", {"succeeded": True}, ref), source="pytest failing test")

        # Behavioral corpus: exact stdout only, no substring/semantic matching.
        behavior_ok = make_runtime(root, "behavior-ok")
        ref = execute(behavior_ok, f"{py} -c \"print('READY')\"")
        record(outcomes, case_id="behavior_exact", claim_class="software.behavioral_acceptance", gold=True,
               predicted=predict(behavior_ok, "software.behavioral_acceptance.cli", {"stdout_equals": "READY\n"}, ref), source="real CLI stdout")

        behavior_near = make_runtime(root, "behavior-near")
        ref = execute(behavior_near, f"{py} -c \"print('READY!')\"")
        record(outcomes, case_id="behavior_near_match", claim_class="software.behavioral_acceptance", gold=False,
               predicted=predict(behavior_near, "software.behavioral_acceptance.cli", {"stdout_equals": "READY\n"}, ref), source="near-match CLI stdout")

        behavior_failed = make_runtime(root, "behavior-failed")
        ref = execute(behavior_failed, f"{py} -c \"print('READY'); raise SystemExit(3)\"")
        record(outcomes, case_id="behavior_output_but_nonzero", claim_class="software.behavioral_acceptance", gold=False,
               predicted=predict(behavior_failed, "software.behavioral_acceptance.cli", {"stdout_equals": "READY\n"}, ref), source="matching stdout with failed process")

        # Adversarial schema/authority cases.
        freeform = make_runtime(root, "freeform")
        ref = execute(freeform, f"{py} -c \"raise SystemExit(0)\"")
        record(outcomes, case_id="freeform_build_claim", claim_class="software.build_result", gold=False,
               predicted=predict(freeform, "software.build_result.compile", "passed", ref), source="valid execution + free-form candidate")

        masquerade = make_runtime(root, "masquerade")
        ref = execute(masquerade, f"{py} -c \"raise SystemExit(0)\"")
        generic_candidate = {"kind": "artifact_json_assertion", "path": ["ok"], "operator": "eq", "expected": True}
        record(outcomes, case_id="generic_assertion_semantic_masquerade", claim_class="software.build_result", gold=False,
               predicted=predict(masquerade, "software.build_result.compile", generic_candidate, ref), source="generic assertion under semantic prefix")

        substitution = make_runtime(root, "substitution")
        ref = execute(substitution, f"{py} -c \"raise SystemExit(0)\"")
        substitution.state.artifacts.remove(ref)
        record(outcomes, case_id="unregistered_evidence_ref", claim_class="software.build_result", gold=False,
               predicted=predict(substitution, "software.build_result.compile", {"succeeded": True}, ref), source="physical artifact removed from state registry")

        tamper = make_runtime(root, "tamper")
        ref = execute(tamper, f"{py} -c \"raise SystemExit(0)\"")
        ArtifactStore.resolve_ref_path(tamper.artifacts.root, ref).write_text("tampered", encoding="utf-8")
        record(outcomes, case_id="tampered_evidence", claim_class="software.build_result", gold=False,
               predicted=predict(tamper, "software.build_result.compile", {"succeeded": True}, ref), source="post-admission artifact tamper")

        unknown = make_runtime(root, "unknown")
        ref = execute(unknown, f"{py} -c \"raise SystemExit(0)\"")
        record(outcomes, case_id="unknown_security_property_class", claim_class="unregistered", gold=False,
               predicted=predict(unknown, "software.security_property.safe", {"succeeded": True}, ref), source="unknown semantic prefix")

        tp = sum(1 for x in outcomes if x["gold"] and x["predicted"])
        tn = sum(1 for x in outcomes if not x["gold"] and not x["predicted"])
        fp = sum(1 for x in outcomes if not x["gold"] and x["predicted"])
        fn = sum(1 for x in outcomes if x["gold"] and not x["predicted"])
        positive_classes = sorted({x["claim_class"] for x in outcomes if x["gold"] and x["predicted"]})
        summary = {
            "benchmark": "stage4-repository-execution-semantics-v1",
            "cases": len(outcomes),
            "true_positives": tp,
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn,
            "positive_claim_classes": positive_classes,
            "all_passed": len(outcomes) >= 12 and fp == 0 and fn == 0 and len(positive_classes) >= 3,
        }
        print(json.dumps({"outcomes": outcomes, "summary": summary}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
