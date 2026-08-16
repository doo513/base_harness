from __future__ import annotations

import hashlib
import json
from typing import Any

from harness.core.storage import IntegrityError
from harness.core.verification import (
    VerificationLevel,
    VerificationResult,
    _verified_artifact_json,
)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _SoftwareExecutionEvidenceVerifier:
    level = VerificationLevel.EXECUTION
    claim_class = ""
    key_prefix = ""
    covers: tuple[str, ...] = ()

    def _load(self, context: dict) -> tuple[dict[str, Any] | None, list[str], str | None]:
        refs = list(context.get("claim_evidence_refs", []))
        artifact_root = context.get("artifact_root")
        claim_key = context.get("claim_key")
        claim_class = context.get("claim_class")

        if claim_class != self.claim_class:
            return None, refs, f"verifier requires claim class {self.claim_class}"
        if not isinstance(claim_key, str) or not claim_key.startswith(self.key_prefix):
            return None, refs, f"verifier requires claim prefix {self.key_prefix}"
        if len(refs) != 1 or not artifact_root:
            return None, refs, "exactly one integrity-verifiable tool-observation artifact is required"

        try:
            raw = _verified_artifact_json(artifact_root, refs[0])
        except Exception as exc:
            return None, refs, f"tool-observation evidence could not be verified: {type(exc).__name__}: {exc}"
        if not isinstance(raw, dict):
            return None, refs, "tool-observation artifact must be an object"
        if not isinstance(raw.get("ok"), bool):
            return None, refs, "tool-observation artifact requires boolean ok"
        output = raw.get("output")
        if not isinstance(output, dict):
            return None, refs, "tool-observation artifact requires command output object"
        returncode = output.get("returncode")
        timed_out = output.get("timed_out")
        stdout = output.get("stdout")
        stderr = output.get("stderr")
        if not isinstance(returncode, int) or isinstance(returncode, bool):
            return None, refs, "command output requires integer returncode"
        if not isinstance(timed_out, bool):
            return None, refs, "command output requires boolean timed_out"
        if not isinstance(stdout, str) or not isinstance(stderr, str):
            return None, refs, "command output requires string stdout/stderr"
        return raw, refs, None

    @staticmethod
    def _execution_success(raw: dict[str, Any]) -> bool:
        output = raw["output"]
        return raw["ok"] is True and output["returncode"] == 0 and output["timed_out"] is False


class _SoftwareBooleanExecutionResultVerifier(_SoftwareExecutionEvidenceVerifier):
    def verify(self, candidate, context):
        raw, refs, error = self._load(context)
        if error is not None:
            return VerificationResult(False, self.level, error, evidence_refs=refs)
        if not isinstance(candidate, dict) or set(candidate) != {"succeeded"} or not isinstance(candidate.get("succeeded"), bool):
            return VerificationResult(
                False,
                self.level,
                "software execution-result claim must be exactly {'succeeded': boolean}",
                evidence_refs=refs,
            )

        assert raw is not None
        actual = self._execution_success(raw)
        expected = candidate["succeeded"]
        ok = actual == expected
        output = raw["output"]
        return VerificationResult(
            ok,
            self.level,
            "software execution-result claim matches verified tool evidence" if ok else "software execution-result claim contradicts verified tool evidence",
            evidence_refs=refs,
            details={
                "actual_succeeded": actual,
                "expected_succeeded": expected,
                "returncode": output["returncode"],
                "timed_out": output["timed_out"],
                "stdout_hash": _stable_hash(output["stdout"]),
                "stderr_hash": _stable_hash(output["stderr"]),
            },
            confidence=1.0,
        )


class SoftwareBuildResultVerifier(_SoftwareBooleanExecutionResultVerifier):
    name = "software_build_result"
    claim_class = "software.build_result"
    key_prefix = "software.build_result."
    covers = ("software_build_execution",)


class SoftwareTestResultVerifier(_SoftwareBooleanExecutionResultVerifier):
    name = "software_test_result"
    claim_class = "software.test_result"
    key_prefix = "software.test_result."
    covers = ("software_test_execution",)


class SoftwareBehavioralAcceptanceVerifier(_SoftwareExecutionEvidenceVerifier):
    name = "software_behavioral_acceptance"
    claim_class = "software.behavioral_acceptance"
    key_prefix = "software.behavioral_acceptance."
    covers = ("software_behavior_execution",)

    def verify(self, candidate, context):
        raw, refs, error = self._load(context)
        if error is not None:
            return VerificationResult(False, self.level, error, evidence_refs=refs)
        if not isinstance(candidate, dict) or set(candidate) != {"stdout_equals"} or not isinstance(candidate.get("stdout_equals"), str):
            return VerificationResult(
                False,
                self.level,
                "behavioral claim must be exactly {'stdout_equals': string}",
                evidence_refs=refs,
            )

        assert raw is not None
        output = raw["output"]
        successful = self._execution_success(raw)
        expected = candidate["stdout_equals"]
        actual = output["stdout"]
        ok = successful and actual == expected
        return VerificationResult(
            ok,
            self.level,
            "behavioral stdout exactly matches successful verified execution" if ok else "behavioral stdout does not exactly match a successful verified execution",
            evidence_refs=refs,
            details={
                "execution_succeeded": successful,
                "actual_stdout_hash": _stable_hash(actual),
                "expected_stdout_hash": _stable_hash(expected),
                "returncode": output["returncode"],
                "timed_out": output["timed_out"],
            },
            confidence=1.0,
        )
