from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.storage import ArtifactStore
from harness.core.verification import (
    EvidenceRefVerifier,
    ExistsVerifier,
    StructuredArtifactAssertionVerifier,
    VerificationContract,
    VerificationLevel,
    VerificationRequirement,
    VerificationResult,
    VerifierChain,
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vsh-stage4-") as td:
        root = Path(td)
        store = ArtifactStore(root / "artifacts")
        ref = store.put_json("execution.json", {
            "ok": True,
            "output": {"returncode": 0, "stdout": "PASS"},
            "meta": [3, 5],
        })
        ctx = {
            "state": {"artifacts": [ref]},
            "claim_evidence_refs": [ref],
            "artifact_root": str(store.root),
            "claim_key": "probe",
        }
        contract = VerificationContract(
            VerificationLevel.EXECUTION,
            (
                VerificationRequirement("candidate_exists", VerificationLevel.SCHEMA),
                VerificationRequirement("evidence_present", VerificationLevel.STRUCTURAL, require_evidence=True),
                VerificationRequirement("artifact_semantics", VerificationLevel.EXECUTION, require_evidence=True, minimum_confidence=1.0),
            ),
        )
        chain = VerifierChain([ExistsVerifier(), EvidenceRefVerifier(), StructuredArtifactAssertionVerifier()])
        cases = [
            ({"kind": "artifact_json_assertion", "path": ["output", "returncode"], "operator": "eq", "expected": 0}, True, "returncode_positive"),
            ({"kind": "artifact_json_assertion", "path": ["output", "returncode"], "operator": "eq", "expected": 1}, False, "returncode_negative"),
            ({"kind": "artifact_json_assertion", "path": ["output", "stdout"], "operator": "eq", "expected": "PASS"}, True, "stdout_positive"),
            ({"kind": "artifact_json_assertion", "path": ["output", "stdout"], "operator": "eq", "expected": "FAIL"}, False, "stdout_negative"),
            ({"kind": "artifact_json_assertion", "path": ["meta", 1], "operator": "eq", "expected": 5}, True, "list_positive"),
            ({"kind": "artifact_json_assertion", "path": ["meta", 1], "operator": "eq", "expected": 3}, False, "list_negative"),
            ("free-form semantic claim", False, "freeform_rejected"),
            ({"kind": "artifact_json_assertion", "path": ["missing"], "operator": "eq", "expected": 1}, False, "missing_path_rejected"),
        ]
        outcomes = []
        fp = fn = 0
        for candidate, gold, case_id in cases:
            results = chain.run(candidate, ctx)
            predicted = contract.assess(results).accepted
            fp += int(predicted and not gold)
            fn += int((not predicted) and gold)
            outcomes.append({"id": case_id, "gold": gold, "predicted": predicted, "pass": predicted == gold})

        class Inflating:
            name = "inflating"
            level = VerificationLevel.STRUCTURAL
            covers = ("artifact_semantics",)
            def verify(self, candidate, context):
                return VerificationResult(True, VerificationLevel.EXTERNAL_ORACLE, "fake")

        inflation_blocked = not VerifierChain([Inflating()]).run("x", {})[0].verified
        summary = {
            "stage": "04",
            "matrix_cases": len(cases),
            "false_positives": fp,
            "false_negatives": fn,
            "level_inflation_blocked": inflation_blocked,
            "all_cases_pass": all(x["pass"] for x in outcomes),
            "outcomes": outcomes,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if fp == 0 and fn == 0 and inflation_blocked and summary["all_cases_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
