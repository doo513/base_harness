from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.storage import ArtifactStore
from harness.core.verification import EvidenceRefVerifier, ExistsVerifier, StructuredArtifactAssertionVerifier, VerificationContract, VerificationLevel, VerificationRequirement, VerificationResult, VerifierChain


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vsh-stage4-") as td:
        root = Path(td)
        store = ArtifactStore(root / "artifacts")
        ref = store.put_json("execution.json", {"ok": True, "output": {"returncode": 0, "stdout": "PASS"}, "meta": [3, 5]})
        ctx = {"state": {"artifacts": [ref]}, "claim_evidence_refs": [ref], "artifact_root": str(store.root), "claim_key": "artifact_assertion.probe"}
        contract = VerificationContract(VerificationLevel.EXECUTION, (
            VerificationRequirement("candidate_exists", VerificationLevel.SCHEMA),
            VerificationRequirement("evidence_present", VerificationLevel.STRUCTURAL, require_evidence=True),
            VerificationRequirement("artifact_semantics", VerificationLevel.EXECUTION, require_evidence=True, minimum_confidence=1.0),
        ))
        chain = VerifierChain([ExistsVerifier(), EvidenceRefVerifier(), StructuredArtifactAssertionVerifier()])
        def a(expected, path): return {"kind": "artifact_json_assertion", "path": path, "operator": "eq", "expected": expected}
        cases = [
            (a(0, ["output", "returncode"]), True, "returncode_positive"),
            (a(1, ["output", "returncode"]), False, "returncode_negative"),
            (a("PASS", ["output", "stdout"]), True, "stdout_positive"),
            (a("FAIL", ["output", "stdout"]), False, "stdout_negative"),
            (a(5, ["meta", 1]), True, "list_positive"),
            (a(3, ["meta", 1]), False, "list_negative"),
            ("free-form semantic claim", False, "freeform_rejected"),
            (a(1, ["missing"]), False, "missing_path_rejected"),
        ]
        outcomes = []
        fp = fn = 0
        for candidate, gold, case_id in cases:
            predicted = contract.assess(chain.run(candidate, ctx)).accepted
            fp += int(predicted and not gold)
            fn += int((not predicted) and gold)
            outcomes.append({"id": case_id, "gold": gold, "predicted": predicted, "pass": predicted == gold})

        class Inflating:
            name = "inflating"
            level = VerificationLevel.STRUCTURAL
            covers = ("artifact_semantics",)
            def verify(self, candidate, context): return VerificationResult(True, VerificationLevel.EXTERNAL_ORACLE, "fake")
        inflation_blocked = not VerifierChain([Inflating()]).run("x", {})[0].verified

        masquerade_ctx = dict(ctx)
        masquerade_ctx["claim_key"] = "security.sql_injection_success"
        masquerade_blocked = not contract.assess(chain.run(a(0, ["output", "returncode"]), masquerade_ctx)).accepted

        original = store.resolve(ref).read_text(encoding="utf-8")
        store.resolve(ref).write_text(json.dumps({"ok": True, "output": {"returncode": 9}}), encoding="utf-8")
        tamper_blocked = not contract.assess(chain.run(a(9, ["output", "returncode"]), ctx)).accepted
        store.resolve(ref).write_text(original, encoding="utf-8")

        summary = {
            "stage": "04",
            "matrix_cases": len(cases),
            "false_positives": fp,
            "false_negatives": fn,
            "level_inflation_blocked": inflation_blocked,
            "semantic_key_masquerade_blocked": masquerade_blocked,
            "artifact_tamper_blocked": tamper_blocked,
            "all_cases_pass": all(x["pass"] for x in outcomes),
            "outcomes": outcomes,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if fp == 0 and fn == 0 and inflation_blocked and masquerade_blocked and tamper_blocked and summary["all_cases_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
