from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from .verification_v2 import PROTOCOL_VERSION, ProtocolError, VerificationEngine


VerifiedSidecar = VerificationEngine


def _response(
    envelope: dict[str, Any],
    payload: dict[str, Any],
    response_type: str = "response",
) -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "id": str(envelope.get("id", "")),
        "runId": str(envelope.get("runId", "")),
        "scopeId": str(envelope.get("scopeId", "")),
        "type": response_type,
        "payload": payload,
    }


def serve(
    input_stream: TextIO,
    output_stream: TextIO,
    sidecar: VerificationEngine | None = None,
) -> int:
    verifier = sidecar or VerificationEngine()
    for line in input_stream:
        if not line.strip():
            continue
        envelope: dict[str, Any] = {}
        try:
            decoded = json.loads(line)
            if not isinstance(decoded, dict):
                raise ProtocolError("NDJSON message must be an object")
            envelope = decoded
            payload = verifier.handle(envelope)
            response = _response(envelope, payload)
        except ProtocolError as error:
            failure_kind = (
                "harness_protocol_version_mismatch"
                if "version mismatch" in str(error)
                else "harness_protocol_error"
            )
            response = _response(
                envelope,
                {
                    "outcome": "failure",
                    "state": "failure",
                    "failureKind": failure_kind,
                    "message": str(error),
                },
                "failure",
            )
        except Exception as error:
            response = _response(
                envelope,
                {
                    "outcome": "failure",
                    "state": "failure",
                    "failureKind": "harness_verifier_error",
                    "message": str(error),
                },
                "failure",
            )
        output_stream.write(
            json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
        output_stream.flush()
    return 0


def main() -> int:
    return serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
