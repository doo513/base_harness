from __future__ import annotations

from harness.core.verification import VerificationLevel, VerificationResult, _verified_artifact_json


class _HackathonExecutionCheckVerifier:
    level = VerificationLevel.EXECUTION
    claim_class = ""
    key_prefix = ""
    covers: tuple[str, ...] = ()

    def verify(self, candidate, context):
        refs = list(context.get("claim_evidence_refs", []))
        artifact_root = context.get("artifact_root")
        claim_key = context.get("claim_key")
        claim_class = context.get("claim_class")
        if claim_class != self.claim_class:
            return VerificationResult(False, self.level, f"verifier requires claim class {self.claim_class}", evidence_refs=refs)
        if not isinstance(claim_key, str) or not claim_key.startswith(self.key_prefix):
            return VerificationResult(False, self.level, f"verifier requires claim prefix {self.key_prefix}", evidence_refs=refs)
        if len(refs) != 1 or not artifact_root:
            return VerificationResult(False, self.level, "exactly one integrity-verifiable execution artifact is required", evidence_refs=refs)
        if not isinstance(candidate, dict) or set(candidate) != {"succeeded"} or not isinstance(candidate.get("succeeded"), bool):
            return VerificationResult(False, self.level, "hackathon execution-check claim must be exactly {'succeeded': boolean}", evidence_refs=refs)
        try:
            raw = _verified_artifact_json(artifact_root, refs[0])
        except Exception as exc:
            return VerificationResult(False, self.level, f"execution evidence could not be verified: {type(exc).__name__}: {exc}", evidence_refs=refs)
        if not isinstance(raw, dict) or not isinstance(raw.get("ok"), bool):
            return VerificationResult(False, self.level, "execution artifact must contain boolean ok", evidence_refs=refs)
        output = raw.get("output")
        if not isinstance(output, dict):
            return VerificationResult(False, self.level, "execution artifact requires command output", evidence_refs=refs)
        returncode = output.get("returncode")
        timed_out = output.get("timed_out")
        if not isinstance(returncode, int) or isinstance(returncode, bool) or not isinstance(timed_out, bool):
            return VerificationResult(False, self.level, "execution output requires returncode/timed_out", evidence_refs=refs)
        actual = raw["ok"] is True and returncode == 0 and timed_out is False
        expected = candidate["succeeded"]
        ok = actual == expected
        return VerificationResult(
            ok,
            self.level,
            "hackathon execution-check claim matches verified execution evidence" if ok else "hackathon execution-check claim contradicts verified execution evidence",
            evidence_refs=refs,
            details={"actual_succeeded": actual, "expected_succeeded": expected, "returncode": returncode, "timed_out": timed_out},
            confidence=1.0,
        )


class HackathonBuildCheckVerifier(_HackathonExecutionCheckVerifier):
    name = "hackathon_build_check"
    claim_class = "hackathon.build_check"
    key_prefix = "hackathon.build_check."
    covers = ("hackathon_build_execution",)


class HackathonDemoCheckVerifier(_HackathonExecutionCheckVerifier):
    name = "hackathon_demo_check"
    claim_class = "hackathon.demo_check"
    key_prefix = "hackathon.demo_check."
    covers = ("hackathon_demo_execution",)


class HackathonRehearsalCheckVerifier(_HackathonExecutionCheckVerifier):
    name = "hackathon_rehearsal_check"
    claim_class = "hackathon.rehearsal_check"
    key_prefix = "hackathon.rehearsal_check."
    covers = ("hackathon_rehearsal_execution",)
